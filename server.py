import json
import os
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

import database

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


class DojoHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message, status=400):
        self._send_json({'success': False, 'error': message}, status)

    def _send_success(self, data=None):
        resp = {'success': True}
        if data is not None:
            resp['data'] = data
        self._send_json(resp)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def _serve_static(self, path):
        if path == '/':
            path = '/index.html'
        filepath = os.path.join(STATIC_DIR, path.lstrip('/'))
        realpath = os.path.realpath(filepath)
        real_static = os.path.realpath(STATIC_DIR)
        if not realpath.startswith(real_static):
            self.send_error(403)
            return
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        mtype, _ = mimetypes.guess_type(filepath)
        if not mtype:
            mtype = 'application/octet-stream'
        with open(filepath, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', mtype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == '/' or path.startswith('/static/') or path.endswith('.html') or path.endswith('.js') or path.endswith('.css'):
                self._serve_static(path)
                return

            if path == '/api/meta':
                self._send_success({
                    'belt_order': database.BELT_ORDER,
                    'age_groups': database.AGE_GROUPS,
                    'student_status': database.STUDENT_STATUS,
                    'class_types': database.CLASS_TYPES,
                    'exam_results': database.EXAM_RESULTS,
                    'today': datetime.now().strftime('%Y-%m-%d'),
                    'this_month': datetime.now().strftime('%Y-%m')
                })
                return

            if path == '/api/students':
                status = query.get('status', [None])[0]
                self._send_success(database.list_students(status))
                return

            if path.startswith('/api/students/'):
                sid = int(path.rsplit('/', 1)[-1])
                s = database.get_student(sid)
                if not s:
                    self._send_error('学员不存在', 404)
                    return
                self._send_success(s)
                return

            if path == '/api/attendances':
                date_from = query.get('date_from', [None])[0]
                date_to = query.get('date_to', [None])[0]
                sid = query.get('student_id', [None])[0]
                sid = int(sid) if sid else None
                self._send_success(database.list_attendances(date_from, date_to, sid))
                return

            if path == '/api/exams':
                sid = query.get('student_id', [None])[0]
                sid = int(sid) if sid else None
                self._send_success(database.list_exams(sid))
                return

            if path == '/api/stats/monthly_attendance':
                sid = query.get('student_id', [None])[0]
                ym = query.get('year_month', [None])[0]
                if not sid:
                    self._send_error('缺少 student_id 参数')
                    return
                if not ym:
                    ym = datetime.now().strftime('%Y-%m')
                self._send_success(database.get_student_monthly_attendance(int(sid), ym))
                return

            if path == '/api/stats/belt_distribution':
                ym = query.get('year_month', [None])[0]
                self._send_success(database.get_belt_distribution(ym))
                return

            self._send_error('接口不存在', 404)
        except Exception as e:
            self._send_error(str(e), 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        try:
            if path == '/api/students':
                required = ['nickname', 'phone', 'age_group']
                for f in required:
                    if f not in body or not str(body[f]).strip():
                        self._send_error(f'缺少参数: {f}')
                        return
                sid = database.add_student(
                    body['nickname'].strip(),
                    body['phone'].strip(),
                    body['age_group'],
                    body.get('current_belt', '白'),
                    body.get('status', '在籍')
                )
                self._send_success({'id': sid})
                return

            if path.startswith('/api/students/') and path.endswith('/delete'):
                sid = int(path.split('/')[-2])
                database.delete_student(sid)
                self._send_success()
                return

            if path == '/api/attendances':
                required = ['date', 'student_id', 'class_type']
                for f in required:
                    if f not in body:
                        self._send_error(f'缺少参数: {f}')
                        return
                aid = database.add_attendance(
                    body['date'],
                    int(body['student_id']),
                    body['class_type']
                )
                self._send_success({'id': aid})
                return

            if path == '/api/exams':
                required = ['student_id', 'exam_date', 'target_belt', 'result']
                for f in required:
                    if f not in body:
                        self._send_error(f'缺少参数: {f}')
                        return
                eid = database.add_exam(
                    int(body['student_id']),
                    body['exam_date'],
                    body['target_belt'],
                    body['result']
                )
                self._send_success({'id': eid})
                return

            self._send_error('接口不存在', 404)
        except ValueError as e:
            self._send_error(str(e))
        except Exception as e:
            self._send_error(str(e), 500)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        try:
            if path.startswith('/api/students/'):
                sid = int(path.rsplit('/', 1)[-1])
                fields = {}
                for k in ['nickname', 'phone', 'age_group', 'current_belt', 'status']:
                    if k in body:
                        if isinstance(body[k], str):
                            fields[k] = body[k].strip() or None
                        else:
                            fields[k] = body[k]
                fields = {k: v for k, v in fields.items() if v is not None}
                database.update_student(sid, **fields)
                self._send_success()
                return

            self._send_error('接口不存在', 404)
        except ValueError as e:
            self._send_error(str(e))
        except Exception as e:
            self._send_error(str(e), 500)


def main():
    database.init_db()
    server = HTTPServer(('localhost', 7294), DojoHandler)
    print('空手道道场管理系统已启动')
    print('访问地址: http://localhost:7294')
    print('按 Ctrl+C 停止服务器')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务器已停止')
        server.server_close()


if __name__ == '__main__':
    main()
