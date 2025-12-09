from flask import Flask, jsonify, request, send_from_directory, abort
import sqlite3
import json
from pathlib import Path


DB_PATH = "mydata.db"
DEPTS_PATH = "static/departments.json"
STATIC_FOLDER = "static"

app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path="/static")

def load_departments():
    text = Path(DEPTS_PATH).read_text(encoding="utf-8")
    data = json.loads(text)
    return data


def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    return conn

def parse_flags(raw):
    if not raw:
        return []
    try:
        f = json.loads(raw)
        if isinstance(f, str):
            return [f]
        if isinstance(f, list):
            return [str(x) for x in f]
    except Exception:
        return [raw] if raw else []
    return []

def employee_to_public(emp_row, departments):
    flags = parse_flags(emp_row.get("flags"))
    active = flags[-1] if flags else "general"
    dept_cfg = departments.get(active, departments.get("general", {}))
    return {
        "id": emp_row["id"],
        "name": emp_row["name"],
        "flags": flags,
        "active_department": active,
        "department_info": dept_cfg,
    }


@app.route("/")
def root():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/employees", methods=["GET"])
def api_list_employees():
    depts = load_departments()
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, flags FROM employees ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        emp = employee_to_public(r, depts)
        flags = emp.get("flags", [])
        if flags:
            dept = flags[-1]
            info = depts.get(dept, {})
            emp.update({
                "salary": info.get("salary"),
                "bonus_percent": info.get("bonus_percent"),
                "days_off": info.get("days_off")
            })
        out.append(emp)
    return jsonify(out)

@app.route("/api/employee/<int:emp_id>", methods=["GET"])
def api_get_employee(emp_id):
    depts = load_departments()
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, flags FROM employees WHERE id = ?", (emp_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    emp = employee_to_public(row, depts)
    flags = emp.get("flags", [])
    if flags:
        dept = flags[-1]
        info = depts.get(dept, {})
        emp.update({
            "salary": info.get("salary"),
            "bonus_percent": info.get("bonus_percent"),
            "days_off": info.get("days_off")
        })
    return jsonify(emp)


@app.route("/api/employee/<int:emp_id>/flags", methods=["PATCH"])
def api_update_flags(emp_id):
    if not request.is_json:
        return jsonify({"error": "expected json body"}), 400
    body = request.get_json()
    if "flags" not in body:
        return jsonify({"error": "missing 'flags' field"}), 400
    flags = body["flags"]
    if not isinstance(flags, list):
        return jsonify({"error": "'flags' must be a list"}), 400

    flags = [str(x) for x in flags]

    depts = load_departments()
    unknown = [f for f in flags if f not in depts]
    if unknown:
        warning = f"Unknown departments: {unknown}"
    else:
        warning = None

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM employees WHERE id = ?", (emp_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "employee not found"}), 404

    flags_json = json.dumps(flags, ensure_ascii=False)
    cur.execute("UPDATE employees SET flags = ? WHERE id = ?", (flags_json, emp_id))
    conn.commit()
    conn.close()

    resp = {"id": emp_id, "flags": flags}
    if warning:
        resp["warning"] = warning
    return jsonify(resp)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)