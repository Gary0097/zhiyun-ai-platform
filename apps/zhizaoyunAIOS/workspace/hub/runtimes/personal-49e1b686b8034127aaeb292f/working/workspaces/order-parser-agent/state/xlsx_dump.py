#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal xlsx reader using stdlib only (zipfile + ElementTree)."""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'rel': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'pkgrel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}

def col_to_idx(col):
    idx = 0
    for ch in col:
        idx = idx * 26 + (ord(ch) - 64)
    return idx  # 1-based

def load(path):
    z = zipfile.ZipFile(path)
    # shared strings
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in root.findall('main:si', NS):
            texts = [t.text or '' for t in si.iter('{%s}t' % NS['main'])]
            shared.append(''.join(texts))
    # workbook sheets -> rels
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rid2target = {r.get('Id'): r.get('Target') for r in rels}
    sheets = []
    for sh in wb.findall('main:sheets/main:sheet', NS):
        rid = sh.get('{%s}id' % NS['rel'])
        target = rid2target[rid]
        if not target.startswith('xl/'):
            target = 'xl/' + target.lstrip('/')
        sheets.append((sh.get('name'), target))
    return z, shared, sheets

def dump_sheet(z, shared, target):
    root = ET.fromstring(z.read(target))
    # merge cells
    merges = [m.get('ref') for m in root.iter('{%s}mergeCell' % NS['main'])]
    rows = {}
    maxcol = 0
    for row in root.iter('{%s}row' % NS['main']):
        r = int(row.get('r'))
        for c in row.findall('main:c', NS):
            ref = c.get('r')
            m = re.match(r'([A-Z]+)(\d+)', ref)
            col = col_to_idx(m.group(1))
            t = c.get('t')
            v = c.find('main:v', NS)
            is_node = c.find('main:is', NS)
            val = None
            if t == 's' and v is not None:
                val = shared[int(v.text)]
            elif t == 'inlineStr' and is_node is not None:
                val = ''.join(x.text or '' for x in is_node.iter('{%s}t' % NS['main']))
            elif v is not None:
                val = v.text
            f = c.find('main:f', NS)
            if val is None and f is not None:
                val = '=' + (f.text or '')
            if val is not None and str(val).strip() != '':
                rows.setdefault(r, {})[col] = str(val)
                maxcol = max(maxcol, col)
    print(f'--- rows: {len(rows)}, merges: {merges}')
    for r in sorted(rows):
        cells = rows[r]
        line = ' | '.join(f'{c}:{cells[c]}' for c in sorted(cells))
        print(f'R{r}: {line}')

if __name__ == '__main__':
    path = sys.argv[1]
    z, shared, sheets = load(path)
    print('SHEETS:', [s[0] for s in sheets])
    for name, target in sheets:
        print(f'\n===== SHEET "{name}" ({target}) =====')
        dump_sheet(z, shared, target)
