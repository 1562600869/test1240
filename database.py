import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dojo.db')

BELT_ORDER = ['白', '黄', '橙', '绿', '蓝', '紫', '棕', '黑']
AGE_GROUPS = ['儿童', '青少年', '成人']
STUDENT_STATUS = ['在籍', '停课', '退出']
CLASS_TYPES = ['基础课', '晋级课', '自由课']
EXAM_RESULTS = ['通过', '未通过']


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT NOT NULL,
                phone TEXT NOT NULL,
                age_group TEXT NOT NULL CHECK(age_group IN ('儿童','青少年','成人')),
                current_belt TEXT NOT NULL DEFAULT '白' CHECK(current_belt IN ('白','黄','橙','绿','蓝','紫','棕','黑')),
                status TEXT NOT NULL DEFAULT '在籍' CHECK(status IN ('在籍','停课','退出')),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS attendances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                student_id INTEGER NOT NULL,
                class_type TEXT NOT NULL CHECK(class_type IN ('基础课','晋级课','自由课')),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                UNIQUE(date, student_id, class_type)
            );

            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                exam_date TEXT NOT NULL,
                target_belt TEXT NOT NULL CHECK(target_belt IN ('白','黄','橙','绿','蓝','紫','棕','黑')),
                result TEXT NOT NULL CHECK(result IN ('通过','未通过')),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_attendances_date ON attendances(date);
            CREATE INDEX IF NOT EXISTS idx_attendances_student ON attendances(student_id);
            CREATE INDEX IF NOT EXISTS idx_exams_student ON exams(student_id);
            CREATE INDEX IF NOT EXISTS idx_exams_date ON exams(exam_date);
        ''')
        conn.commit()
    finally:
        conn.close()


def get_next_belt(current_belt):
    idx = BELT_ORDER.index(current_belt)
    if idx < len(BELT_ORDER) - 1:
        return BELT_ORDER[idx + 1]
    return None


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


def list_students(status_filter=None):
    conn = get_connection()
    try:
        if status_filter:
            rows = conn.execute(
                'SELECT * FROM students WHERE status = ? ORDER BY id DESC',
                (status_filter,)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM students ORDER BY id DESC'
            ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def get_student(student_id):
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT * FROM students WHERE id = ?',
            (student_id,)
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def add_student(nickname, phone, age_group, current_belt='白', status='在籍'):
    if age_group not in AGE_GROUPS:
        raise ValueError(f'年龄组无效，必须是: {AGE_GROUPS}')
    if current_belt not in BELT_ORDER:
        raise ValueError(f'腰带无效，必须是: {BELT_ORDER}')
    if status not in STUDENT_STATUS:
        raise ValueError(f'状态无效，必须是: {STUDENT_STATUS}')
    conn = get_connection()
    try:
        cur = conn.execute(
            'INSERT INTO students (nickname, phone, age_group, current_belt, status) VALUES (?, ?, ?, ?, ?)',
            (nickname, phone, age_group, current_belt, status)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_student(student_id, nickname=None, phone=None, age_group=None, current_belt=None, status=None):
    fields = []
    values = []
    if nickname is not None:
        fields.append('nickname = ?')
        values.append(nickname)
    if phone is not None:
        fields.append('phone = ?')
        values.append(phone)
    if age_group is not None:
        if age_group not in AGE_GROUPS:
            raise ValueError(f'年龄组无效，必须是: {AGE_GROUPS}')
        fields.append('age_group = ?')
        values.append(age_group)
    if current_belt is not None:
        if current_belt not in BELT_ORDER:
            raise ValueError(f'腰带无效，必须是: {BELT_ORDER}')
        fields.append('current_belt = ?')
        values.append(current_belt)
    if status is not None:
        if status not in STUDENT_STATUS:
            raise ValueError(f'状态无效，必须是: {STUDENT_STATUS}')
        fields.append('status = ?')
        values.append(status)
    if not fields:
        return False
    values.append(student_id)
    conn = get_connection()
    try:
        conn.execute(f'UPDATE students SET {", ".join(fields)} WHERE id = ?', values)
        conn.commit()
        return True
    finally:
        conn.close()


def delete_student(student_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM students WHERE id = ?', (student_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def add_attendance(date_str, student_id, class_type):
    if class_type not in CLASS_TYPES:
        raise ValueError(f'课类型无效，必须是: {CLASS_TYPES}')
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise ValueError('日期格式无效，应为 YYYY-MM-DD')
    conn = get_connection()
    try:
        cur = conn.execute(
            'INSERT INTO attendances (date, student_id, class_type) VALUES (?, ?, ?)',
            (date_str, student_id, class_type)
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError('该学员当天已签到过该类型课程')
    finally:
        conn.close()


def list_attendances(date_from=None, date_to=None, student_id=None):
    conn = get_connection()
    try:
        sql = '''
            SELECT a.*, s.nickname, s.current_belt
            FROM attendances a
            JOIN students s ON a.student_id = s.id
            WHERE 1=1
        '''
        params = []
        if date_from:
            sql += ' AND a.date >= ?'
            params.append(date_from)
        if date_to:
            sql += ' AND a.date <= ?'
            params.append(date_to)
        if student_id:
            sql += ' AND a.student_id = ?'
            params.append(student_id)
        sql += ' ORDER BY a.date DESC, a.id DESC'
        rows = conn.execute(sql, params).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def add_exam(student_id, exam_date, target_belt, result):
    if target_belt not in BELT_ORDER:
        raise ValueError(f'目标腰带无效，必须是: {BELT_ORDER}')
    if result not in EXAM_RESULTS:
        raise ValueError(f'考核结果无效，必须是: {EXAM_RESULTS}')
    try:
        datetime.strptime(exam_date, '%Y-%m-%d')
    except ValueError:
        raise ValueError('日期格式无效，应为 YYYY-MM-DD')

    conn = get_connection()
    try:
        conn.execute('BEGIN')

        student = conn.execute(
            'SELECT current_belt FROM students WHERE id = ?',
            (student_id,)
        ).fetchone()
        if not student:
            conn.rollback()
            raise ValueError('学员不存在')

        current_belt = student['current_belt']
        expected_next = get_next_belt(current_belt)
        if expected_next is None:
            conn.rollback()
            raise ValueError('该学员已是黑带，无法继续晋级')
        if target_belt != expected_next:
            conn.rollback()
            raise ValueError(f'目标腰带必须是下一级：{expected_next}')

        cur = conn.execute(
            'INSERT INTO exams (student_id, exam_date, target_belt, result) VALUES (?, ?, ?, ?)',
            (student_id, exam_date, target_belt, result)
        )
        exam_id = cur.lastrowid

        if result == '通过':
            conn.execute(
                'UPDATE students SET current_belt = ? WHERE id = ?',
                (target_belt, student_id)
            )

        conn.commit()
        return exam_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_exams(student_id=None):
    conn = get_connection()
    try:
        sql = '''
            SELECT e.*, s.nickname, s.current_belt AS current_belt_now
            FROM exams e
            JOIN students s ON e.student_id = s.id
            WHERE 1=1
        '''
        params = []
        if student_id:
            sql += ' AND e.student_id = ?'
            params.append(student_id)
        sql += ' ORDER BY e.exam_date DESC, e.id DESC'
        rows = conn.execute(sql, params).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def get_student_monthly_attendance(student_id, year_month):
    conn = get_connection()
    try:
        sql = '''
            SELECT class_type, COUNT(*) AS count
            FROM attendances
            WHERE student_id = ? AND strftime('%Y-%m', date) = ?
            GROUP BY class_type
        '''
        rows = conn.execute(sql, (student_id, year_month)).fetchall()
        result = {ct: 0 for ct in CLASS_TYPES}
        for r in rows:
            result[r['class_type']] = r['count']
        result['total'] = sum(result.values())
        return result
    finally:
        conn.close()


def get_belt_distribution(year_month=None):
    conn = get_connection()
    try:
        sql = '''
            SELECT current_belt, COUNT(*) AS count
            FROM students
            WHERE status = '在籍'
            GROUP BY current_belt
        '''
        rows = conn.execute(sql).fetchall()
        result = {b: 0 for b in BELT_ORDER}
        for r in rows:
            result[r['current_belt']] = r['count']
        result['total'] = sum(result.values())
        return result
    finally:
        conn.close()
