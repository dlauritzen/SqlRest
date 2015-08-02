
import base64
import json
import pymysql
import sys
import traceback

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

class SqlRestException(Exception):

    def __init__(self, msg, query=None, mysql_err=None, status=400):
        self.msg = msg
        self.status = status
        self.mysql_err = mysql_err
        self.query = query

    def error_dict(self):
        d = {}
        if self.query:
            d['query'] = self.query
        if self.mysql_err:
            d['code'] = self.mysql_err.args[0]
            d['message'] = self.mysql_err.args[1]
        else:
            d['message'] = self.msg
        return d


def get_user(request):
    auth = request.META.get("HTTP_AUTHORIZATION")
    if not auth:
        raise SqlRestException('User is required.', status=401)
    type, token = auth.split(' ', 1)
    if type == 'Basic':
        userpass = base64.b64decode(token).decode('utf-8')
        username, password = userpass.split(':')
        if username.lower() == 'root':
            raise SqlRestException('User root is not allowed.', status=403)
        return username, password
    raise SqlRestException('Invalid authorization type.', status=400)


def parse_path(path):
    command = None
    database = None
    table = None
    id = None
    parts = [x for x in path.split('/') if x]
    while parts:
        part = parts.pop(0)
        if part.startswith('_'):
            if id:
                raise SqlRestException('Invalid path.')
            command = part[1:].lower()
            break
        elif database is None:
            database = part
        elif table is None:
            table = part
        elif id is None:
            id = part
        else:
            raise SqlRestException('Invalid path.')
    return command, database, table, id


def get_list(w, key):
    value = w[key]
    try:
        return json.loads(value)
    except Exception as e:
        return w.getlist(key)


def get_bool(value):
    return value.lower() in ['yes', 'true', 'y', '1']


def escape(value, conn=None):
    if value is None or value in ('null', 'NULL', 'Null', 'None'):
        return 'NULL'
    else:
        try:
            n = float(value)
            return str(value)
        except:
            if conn:
                return conn.escape(value)
            return "'{}'".format(value.replace("'", "\\'"))


def allow_raw_query(q):
    if q:
        queries = [x.strip() for x in q.lower().split(';') if x]
        if len(queries) > 1:
            # Disallow multiple queries in one request
            return False
        for query in queries:
            # Disallow delete or drop queries
            if query.startswith('delete') or query.startswith('drop'):
                return False
    return True


def build_query(conn=None, command=None, database=None, table=None, id=None, w=None, v=None, method='GET'):
    query = None
    params = []
    many = False
    if not command and not database:
        raise SqlRestException('Database or command is required.')
    elif not table and not command:
        raise SqlRestException('Table or database command is required.')

    if command and not database:
        if command == 'databases':
            query = 'SHOW DATABASES'
        else:
            raise SqlRestException('Invalid command.')
    elif command and not table:
        if command == 'tables':
            query = 'SHOW TABLES'
        elif command == 'query':
            if allow_raw_query(v):
                query = v
            else:
                raise SqlRestException('Raw query rejected.')
        else:
            raise SqlRestException('Invalid command.')
    elif command:
        if command == 'describe':
            query = 'DESCRIBE {}'.format(table)
        else:
            raise SqlRestException('Invalid command.')
    if query:
        return query, params, many

    values = []
    if v:
        try:
            values = json.loads(v)
            if isinstance(values, dict):
                values = [values]
            elif not isinstance(values, list):
                raise SqlRestException('Invalid body. Must be a JSON list or dictionary.')
            else:
                for item in values:
                    if not isinstance(item, dict):
                        raise SqlRestException('Invalid body. JSON list must contain only dictionaries.')
        except Exception as e:
            raise SqlRestException('Invalid body: {}'.format(e))

    fields = '*'
    if w and '_fields' in w:
        fields = ', '.join([conn.escape_string(v) for v in get_list(w, '_fields')])
    if id:
        id_field = 'id'
        if w and '_idfield' in w:
            id_field = conn.escape_string(w['_idfield'])
        try:
            id = int(id)
        except:
            pass
        if values:
            # Update
            if len(values) != 1:
                # Cannot do multi-row update
                raise SqlRestException('Invalid body. Single-row update cannot take multiple rows.')
            cols = sorted(values[0].keys())
            params = { key: values[0][key] for key in cols }
            params[id_field] = id
            query = 'UPDATE {table} SET {updates} WHERE {id_field} = %({id_field})s'.format(
                table=table,
                updates=', '.join(['{0} = %({0})s'.format(conn.escape_string(col)) for col in cols]),
                id_field=id_field)
        else:
            params = {}
            params[id_field] = id
            query = 'SELECT {fields} FROM {table} WHERE {id_field} = %({id_field})s'.format(
                fields=fields,
                table=table,
                id_field=id_field)
    else:
        where = []
        if method == 'GET':
            if w:
                params = {}
                for key, value in w.items():
                    if key.startswith('_'): continue
                    operator = '='
                    if '__' in key:
                        original_key = key
                        key, operator = key.split('__')
                        if operator == 'exact':
                            operator = '='
                            params[key] = value
                            value = '%({})s'.format(key)
                        elif operator == 'neq':
                            operator = '!='
                            params[key] = value
                            value = '%({})s'.format(key)
                        elif operator == 'lte':
                            operator = '<='
                            params[key] = value
                            value = '%({})s'.format(key)
                        elif operator == 'gte':
                            operator = '>='
                            params[key] = value
                            value = '%({})s'.format(key)
                        elif operator == 'lt':
                            operator = '<'
                            params[key] = value
                            value = '%({})s'.format(key)
                        elif operator == 'gt':
                            operator = '>'
                            params[key] = value
                            value = '%({})s'.format(key)
                        elif operator == 'in':
                            operator = 'IN'
                            value = '({})'.format(', '.join([escape(v, conn) for v in get_list(w, original_key)]))
                        elif operator == 'notin':
                            operator = 'NOT IN'
                            value = '({})'.format(', '.join([escape(v, conn) for v in get_list(w, original_key)]))
                        elif operator == 'iexact':
                            operator = 'ILIKE'
                            params[key] = value
                            value = '%({})s'.format(key)
                        elif operator == 'contains':
                            operator = 'LIKE'
                            value = '\'%%{}%%\''.format(conn.escape_string(value))
                        elif operator == 'icontains':
                            operator = 'ILIKE'
                            value = '\'%%{}%%\''.format(conn.escape_string(value))
                        elif operator == 'startswith':
                            operator = 'LIKE'
                            value = '\'{}%%\''.format(conn.escape_string(value))
                        elif operator == 'istartswith':
                            operator = 'ILIKE'
                            value = '\'{}%%\''.format(conn.escape_string(value))
                        elif operator == 'endswith':
                            operator = 'LIKE'
                            value = '\'%%{}\''.format(conn.escape_string(value))
                        elif operator == 'iendswith':
                            operator = 'ILIKE'
                            value = '\'%%{}\''.format(conn.escape_string(value))
                        elif operator == 'isnull':
                            value = get_bool(value)
                            operator = 'IS' if value else 'IS NOT'
                            value = 'NULL'
                    else:
                        if value == 'NULL' and operator == '=':
                            operator = 'IS'
                        else:
                            params[key] = value
                            value = '%({})s'.format(key)
                    where.append('{} {} {}'.format(conn.escape_string(key), operator, value))
            query = 'SELECT {} FROM {}'.format(fields, table)
            if where:
                query += ' WHERE {}'.format(' AND '.join(where))
        elif method == 'POST':
            if not values:
                raise SqlRestException('Body required for insert.')
            cols = sorted(values[0].keys())
            query = 'INSERT INTO {table} ({cols}) VALUES ({row})'.format(
                table=table,
                cols=', '.join(cols),
                row=', '.join(['%({})s'.format(col) for col in cols]))
            many = len(values) > 1
            params = []
            for row in values:
                params.append({ col: row[col] for col in cols })
            if len(params) == 1:
                params = params[0]
    return query, params, many


@csrf_exempt
def db_access(request, path):
    conn = None
    data = {
        'request': {}
    }
    try:

        username, password = get_user(request)
        data['request']['user'] = username

        command, database, table, id = parse_path(path)
        data['request']['command'] = command
        data['request']['database'] = database
        data['request']['table'] = table
        data['request']['id'] = id

        conn = pymysql.connect(host='localhost', user=username, password=password, database=database, autocommit=True)

        query, params, many = build_query(conn=conn,
                                          command=command,
                                          database=database,
                                          table=table,
                                          id=id,
                                          w=request.GET,
                                          v=request.body.decode('utf-8'),
                                          method=request.method)
        data['request']['query'] = { 'query': query, 'parameters': params }

        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            if many:
                cursor.executemany(query, params)
            else:
                cursor.execute(query, params)
        except pymysql.err.DatabaseError as e:
            raise SqlRestException('Error executing query.', mysql_err=e)
        result = {
            'rows': cursor.rowcount,
            'data': [],
        }
        for row in cursor.fetchall():
            result['data'].append(row)
        data['result'] = result

    except SqlRestException as e:
        data['error'] = e.error_dict()
        return JsonResponse(data, status=e.status)
    except Exception as e:
        if settings.DEBUG:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            data['error'] = {
                'message': str(e),
                'traceback': traceback.format_tb(exc_traceback),
            }
        else:
            data['error'] = { 'message': str(e) }
        return JsonResponse(data, status=500)
    else:
        return JsonResponse(data, status=200)
    finally:
        if conn:
            conn.close()


def about(request):
    return render(request, 'about.html')
