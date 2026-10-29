import re,sys
# usage: check_dm.py DATA_MODEL.md 001_initial_mvp.sql 002_harden_mvp.sql
sql=open(sys.argv[2],encoding='utf-8').read()+"\n"+open(sys.argv[3],encoding='utf-8').read()
tables={}
for m in re.finditer(r'CREATE TABLE (\w+) \((.*?)\n\);',sql,re.S):
    name,body=m.groups(); cols={}
    for line in body.split('\n'):
        line=line.strip().rstrip(',')
        if not line or line.startswith(('CONSTRAINT','--','PRIMARY','UNIQUE')): continue
        mm=re.match(r'(\w+)\s+([A-Z]+(?:\(\d+(?:,\d+)?\))?)',line)
        if mm and mm.group(1) not in cols: cols[mm.group(1)]=mm.group(2)
    tables[name]=cols
for m in re.finditer(r'ALTER TABLE (\w+)\s+ADD COLUMN (\w+) ([A-Z]+(?:\(\d+(?:,\d+)?\))?)',sql):
    tables[m.group(1)][m.group(2)]=m.group(3)
for m in re.finditer(r'ALTER TABLE (\w+)\s+ALTER COLUMN (\w+) TYPE (\w+)',sql):
    tables[m.group(1)][m.group(2)]=m.group(3)
doc=open(sys.argv[1],encoding='utf-8').read()
tail=doc[doc.index('# MVP Physical Data Model'):]
dtab={}
for m in re.finditer(r'TABLE: (\w+)\n\n\| ستون.*?\n\|---.*?\n((?:\|.*\n)+)',tail):
    cols={}
    for row in m.group(2).strip().split('\n'):
        c=[x.strip() for x in row.strip('|').split('|')]
        cols[c[0]]=c[1]
    dtab[m.group(1)]=cols
bad=0
if set(tables)!=set(dtab): print('TABLE SET DIFF',set(tables)^set(dtab)); bad+=1
for t,c in tables.items():
    d=dtab.get(t,{})
    if set(c)!=set(d): print(t,'COLUMN DIFF sql-only',set(c)-set(d),'doc-only',set(d)-set(c)); bad+=1
    for k in set(c)&set(d):
        norm=lambda x:x.replace('TIMESTAMP WITH TIME ZONE','TIMESTAMPTZ').upper()
        if norm(c[k])!=norm(d[k]): print(t,k,'TYPE',c[k],'vs',d[k]); bad+=1
print('tables sql',len(tables),'doc',len(dtab),'problems',bad)
sys.exit(1 if bad else 0)
