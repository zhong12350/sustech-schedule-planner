"""Web 界面入口 — 无需 Git / 终端，浏览器即可使用"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, render_template, request, jsonify
import secrets

from src.auth import cas_login
from src.scraper import get_semester_info, get_courses_for_selection, fetch_all_courses
from src.solver import solve
from src.ratings import enrich_courses_with_ratings, rank_schedules, score_schedule
from src.filters import filter_courses_for_solve, diagnose_no_solution
from src.course_match import CourseMatchResult

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
app.secret_key = secrets.token_hex(32)

# 内存会话存储（单机使用足够）
_sessions: dict[str, dict] = {}


def _schedule_to_dict(schedule, score, rated, total) -> dict:
    """将课表方案转为 JSON 可序列化格式。"""
    courses = []
    for sec in schedule:
        slots = [
            {"weekday": ts.weekday, "start": ts.start_period, "end": ts.end_period}
            for ts in sec.time_slots
        ]
        courses.append({
            "name": sec.course_name,
            "teacher": sec.teacher,
            "time_slots": slots,
            "rating": sec.rating,
            "review_count": sec.review_count,
            "grading_score": sec.grading_score,
            "gain_score": sec.gain_score,
        })
    return {
        "courses": courses,
        "score": round(score, 2),
        "rated_count": rated,
        "total_count": total,
    }


def _ambiguous_to_dict(ambiguous: list[CourseMatchResult]) -> list[dict]:
    return [
        {
            "query": match.query,
            "options": [
                {
                    "identity": opt.identity,
                    "score": round(opt.score, 2),
                    "section_count": opt.section_count,
                    "teachers": opt.teachers,
                }
                for opt in match.options
            ],
        }
        for match in ambiguous
    ]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/solve", methods=["POST"])
def api_solve():
    data = request.get_json() or {}
    student_id = (data.get("student_id") or "").strip()
    password = data.get("password") or ""
    course_names = data.get("courses") or []
    use_ratings = data.get("use_ratings", True)
    resolutions = data.get("resolutions") or {}
    session_id = data.get("session_id") or ""

    min_rating = data.get("min_rating", 5.0)
    max_sections_per_course = data.get("max_sections_per_course", 12)
    max_results = data.get("max_results", 100)

    if not course_names:
        return jsonify({"ok": False, "error": "请至少添加一门课程"}), 400

    course_names = [c.strip() for c in course_names if c.strip()]
    if not course_names:
        return jsonify({"ok": False, "error": "请至少添加一门课程"}), 400

    # 复用已有会话（歧义消解后的第二次请求）
    cached = _sessions.get(session_id) if session_id else None
    if cached and resolutions:
        headers = cached["headers"]
        semester_info = cached["semester_info"]
        all_courses = cached["all_courses"]
        semester_label = cached["semester_label"]
    else:
        if not student_id or not password:
            return jsonify({"ok": False, "error": "请填写学号和密码"}), 400
        try:
            headers = cas_login(student_id, password)
        except Exception as e:
            return jsonify({"ok": False, "error": f"登录失败: {e}"}), 401

        try:
            semester_info = get_semester_info(headers)
            semester_label = (
                f"{semester_info.get('p_xn', '?')} 第{semester_info.get('p_xq', '?')}学期"
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"获取学期信息失败: {e}"}), 500

        try:
            all_courses = fetch_all_courses(headers, semester_info)
        except Exception as e:
            return jsonify({"ok": False, "error": f"获取课程数据失败: {e}"}), 500

    try:
        selection = get_courses_for_selection(
            headers,
            semester_info,
            course_names,
            resolutions=resolutions,
            all_courses=all_courses,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"课程匹配失败: {e}"}), 500

    if selection.ambiguous:
        sid = secrets.token_hex(16)
        _sessions[sid] = {
            "headers": headers,
            "semester_info": semester_info,
            "all_courses": all_courses,
            "semester_label": semester_label,
        }
        return jsonify({
            "ok": False,
            "needs_disambiguation": True,
            "session_id": sid,
            "semester": semester_label,
            "ambiguous": _ambiguous_to_dict(selection.ambiguous),
            "matched": [c.name for c in selection.courses],
            "not_found": selection.not_found,
        })

    courses = selection.courses

    if not courses:
        return jsonify({
            "ok": False,
            "error": "未找到任何课程，请检查课程名称是否正确",
            "not_found": selection.not_found,
        }), 404

    if use_ratings:
        enrich_courses_with_ratings(courses, verbose=False)

    solve_courses, filter_stats = filter_courses_for_solve(
        courses,
        min_rating=min_rating if use_ratings else None,
        max_sections_per_course=max_sections_per_course,
        keep_unrated=True,
    )

    if not solve_courses:
        return jsonify({
            "ok": False,
            "error": "剪枝后没有可选教学班，请降低评分要求或减少课程",
            "not_found": selection.not_found,
        }), 400

    results = solve(solve_courses, max_results=max_results)

    if not results:
        hints = diagnose_no_solution(solve_courses)
        return jsonify({
            "ok": True,
            "semester": semester_label,
            "total": 0,
            "schedules": [],
            "not_found": selection.not_found,
            "warnings": hints,
            "message": "没有找到无冲突的课表方案，请减少课程后重试",
        })

    if use_ratings:
        ranked = rank_schedules(results)
        schedules = [
            _schedule_to_dict(sch, total, rated, count)
            for sch, total, rated, count in ranked
        ]
    else:
        schedules = []
        for sch in results:
            total, rated, count = score_schedule(sch)
            schedules.append(_schedule_to_dict(sch, total, rated, count))

    sid = secrets.token_hex(16)
    _sessions[sid] = {
        "headers": headers,
        "semester_info": semester_info,
        "results": results,
    }

    warnings: list[str] = []
    if selection.not_found:
        warnings.append(f"以下课程未找到：{', '.join(selection.not_found)}")
    if filter_stats.removed_empty_courses:
        warnings.append(f"{filter_stats.removed_empty_courses} 门课在剪枝后无可选教学班")

    return jsonify({
        "ok": True,
        "session_id": sid,
        "semester": semester_label,
        "total": len(schedules),
        "schedules": schedules,
        "matched_count": len(courses),
        "requested_count": len(course_names),
        "not_found": selection.not_found,
        "warnings": warnings,
    })


def main(host: str = "127.0.0.1", port: int = 5000) -> None:
    print(f"\n  SUSTech Schedule Planner (Web)")
    print(f"  打开浏览器访问: http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
