"""Fixed database operations; runs with the separate inspection identity."""
import json
import os
import sys
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

def inspect(request):
    with psycopg.connect(os.environ["INSPECTION_DATABASE_URL"], row_factory=dict_row,
                         connect_timeout=5, options="-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000") as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user AS role, current_database() AS database, "
                           "rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                           "FROM pg_roles WHERE rolname = current_user")
            role = cursor.fetchone()
            if role["role"] != "inspection" or any(role[k] for k in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls")):
                raise PermissionError("Unsafe inspection role")
            cursor.execute("""
                SELECT has_database_privilege(current_user, current_database(), 'CREATE')
                    OR has_database_privilege(current_user, current_database(), 'TEMP')
                    OR EXISTS (SELECT 1 FROM pg_namespace WHERE has_schema_privilege(current_user, oid, 'CREATE'))
                    OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname=current_user))
                    OR EXISTS (SELECT 1 FROM pg_class c WHERE c.relkind IN ('r','p') AND
                       (has_table_privilege(current_user, c.oid, 'INSERT') OR
                        has_table_privilege(current_user, c.oid, 'UPDATE') OR
                        has_table_privilege(current_user, c.oid, 'DELETE') OR
                        has_table_privilege(current_user, c.oid, 'TRUNCATE'))) AS writable
            """)
            if cursor.fetchone()["writable"]:
                raise PermissionError("Inspection role has write privileges")
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()["transaction_read_only"] != "on":
                raise PermissionError("Read-only transaction required")
            operation = request["operation"]
            if operation == "list_tables":
                cursor.execute("""
                    SELECT c.relname AS table_name FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace=n.oid
                    WHERE n.nspname='public' AND c.relkind IN ('r','p')
                    AND has_table_privilege(current_user,c.oid,'SELECT')
                    ORDER BY c.relname LIMIT 101
                """)
                rows = cursor.fetchall()
            else:
                table = request["table"]
                cursor.execute("""
                    SELECT c.oid, c.relrowsecurity FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace=n.oid
                    WHERE n.nspname='public' AND c.relname=%s AND c.relkind IN ('r','p')
                    AND has_table_privilege(current_user,c.oid,'SELECT')
                """, [table])
                relation = cursor.fetchone()
                if not relation or relation["relrowsecurity"]:
                    raise PermissionError("Table is not an approved plain table")
                if operation == "describe_table":
                    cursor.execute("""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position
                    """, [table])
                    rows = cursor.fetchall()
                elif operation == "list_constraints":
                    cursor.execute("""
                        SELECT conname AS name, contype AS type, pg_get_constraintdef(oid) AS definition
                        FROM pg_constraint WHERE conrelid=%s ORDER BY conname
                    """, [relation["oid"]])
                    rows = cursor.fetchall()
                elif operation == "sample_rows":
                    cursor.execute("""
                        SELECT a.attname, t.typname FROM pg_attribute a JOIN pg_type t ON a.atttypid=t.oid
                        WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum
                    """, [relation["oid"]])
                    columns = {r["attname"]: r["typname"] for r in cursor.fetchall()}
                    selected = request.get("columns") or list(columns)
                    filters = request.get("filters") or {}
                    allowed_types = {"int2", "int4", "int8", "numeric", "varchar", "text", "timestamptz", "timestamp", "bool"}
                    if any(name not in columns or columns[name] not in allowed_types for name in [*selected, *filters]):
                        raise PermissionError("Unsupported columns")
                    clauses, values = [], []
                    for key, value in filters.items():
                        if value is None:
                            clauses.append(sql.SQL("{} IS NULL").format(sql.Identifier(key)))
                        else:
                            clauses.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
                            values.append(value)
                    where = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses) if clauses else sql.SQL("")
                    query = sql.SQL("SELECT {} FROM {}.{}{} ORDER BY {} LIMIT %s").format(
                        sql.SQL(",").join(map(sql.Identifier, selected)), sql.Identifier("public"),
                        sql.Identifier(table), where, sql.SQL(",").join(map(sql.Identifier, selected)))
                    cursor.execute(query, [*values, request["limit"] + 1])
                    rows = cursor.fetchall()
                else:
                    raise ValueError("Unsupported operation")
            limit = request.get("limit", 100)
            return {"database": role["database"], "schema": "public", "role": role["role"],
                    "transaction_read_only": True, "operation": operation,
                    "rows": rows[:limit], "truncated": len(rows) > limit}

def main():
    try:
        request = json.loads(sys.stdin.read(8192))
        print(json.dumps({"status": "ok", "data": inspect(request)}, default=str))
    except PermissionError:
        print(json.dumps({"status": "rejected", "error": {"code": "database_permission_denied",
                                                       "message": "Database role or requested table is not read-only and approved."}}))
    except psycopg.Error as exc:
        print(json.dumps({"status": "error", "error": {"code": "database_error",
                          "message": "PostgreSQL inspection failed.", "sqlstate": exc.sqlstate}}))
    except Exception:
        print(json.dumps({"status": "error", "error": {"code": "database_worker_error",
                                                       "message": "Database inspection could not complete."}}))

if __name__ == "__main__":
    main()
