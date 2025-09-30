import re, sys, io, os, codecs

API = r"C:\maiq_demo\apps\todo_api\main.py"

def ensure_logging(s):
    if not re.search(r'(?m)^\s*import\s+logging\b', s):
        # from typing import ... satırının altına koy
        s = re.sub(r'(?m)^(.*from\s+typing\s+import[^\r\n]*\r?\n)',
                   r'\1import logging\n', s, count=1) or ("import logging\n" + s)
    if not re.search(r'(?m)^\s*logger\s*=\s*logging\.getLogger\(', s):
        # app = FastAPI(...) bloğunun hemen altına koy (bulamazsa başa)
        m = re.search(r'app\s*=\s*FastAPI\([^)]*\)', s, flags=re.S)
        if m:
            i = m.end()
            s = s[:i] + "\nlogger = logging.getLogger(__name__)\n" + s[i:]
        else:
            s = "logger = logging.getLogger(__name__)\n" + s
    return s

def block_with_indent(indent):
    b = (
        indent + 'rows = c.execute(sql, tuple(args)).fetchall()' + "\n" +
        indent + 'con.close()' + "\n\n" +
        indent + 'items = []' + "\n" +
        indent + 'skipped_ids = []' + "\n" +
        indent + 'for row in rows:' + "\n" +
        indent + '    try:' + "\n" +
        indent + '        items.append(_row_to_task(row))' + "\n" +
        indent + '    except Exception as exc:' + "\n" +
        indent + '        task_id = None' + "\n" +
        indent + '        if isinstance(row, sqlite3.Row):' + "\n" +
        indent + '            try:' + "\n" +
        indent + '                task_id = row["id"]' + "\n" +
        indent + '            except Exception:' + "\n" +
        indent + '                pass' + "\n" +
        indent + '        skipped_ids.append(task_id)' + "\n" +
        indent + '        logger.warning("list_tasks: skipping task id=%s due to invalid data: %s", task_id, exc)' + "\n" +
        indent + 'if skipped_ids:' + "\n" +
        indent + '    logger.warning("list_tasks: skipped %d task(s) due to invalid data. ids=%s", len(skipped_ids), skipped_ids)' + "\n" +
        indent + 'return items' + "\n"
    )
    return b

def fix_file(path):
    s = codecs.open(path, 'r', 'utf-8').read()

    # 1) logging ve logger güvence
    s = ensure_logging(s)

    # 2) ÇÖKMENİN KAYNAĞI: rows=...fetchall() satırının tek satıra yapışması
    #    - "collapsed" hali: aynı satırda 'return items' vs. var
    #    - "klasik" hali: 3 satır (rows / con.close / return [ ... ])
    # Önce collapsed desenini dene
    pat_collapsed = re.compile(r'(?m)^(?P<indent>\s*)rows\s*=\s*c\.execute\(.*?fetchall\(\).*?return\s+items.*$')
    m = pat_collapsed.search(s)
    if m:
        indent = m.group('indent')
        s = pat_collapsed.sub(block_with_indent(indent), s, count=1)
        codecs.open(path, 'w', 'utf-8').write(s)
        return True, "collapsed-line replaced"

    # Klasik 3 satırı dene
    pat_three = re.compile(
        r'(?ms)^(?P<indent>\s*)rows\s*=\s*c\.execute\([^)]*\)\.fetchall\(\)\s*\r?\n'
        r'(?P=indent)con\.close\(\)\s*\r?\n'
        r'(?P=indent)return\s+\[\s*_row_to_task\(r\)\s+for\s+r\s+in\s+rows\s*\]'
    )
    m2 = pat_three.search(s)
    if m2:
        indent = m2.group('indent')
        s = pat_three.sub(block_with_indent(indent), s, count=1)
        codecs.open(path, 'w', 'utf-8').write(s)
        return True, "three-line replaced"

    return False, "pattern not found"

ok, msg = fix_file(API)
print({"ok": ok, "msg": msg})
