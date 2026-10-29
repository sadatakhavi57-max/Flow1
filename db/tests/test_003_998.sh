#!/usr/bin/env bash
# Real PostgreSQL tests for migration 003 and seed 998.  Usage: TF_SQL_DIR=<folder with the six files> bash test_003_998.sh
# Files are applied with `psql -1` (one transaction per file) in the runner's order; the runner's own
# discovery/ordering code is exercised separately by test_runner_order.py.
set -u
SQL=${TF_SQL_DIR:?}; HERE=$(cd "$(dirname "$0")" && pwd); TOOLS="$HERE/../tools"
P="psql -X -q -v ON_ERROR_STOP=1"; pass=0; failn=0
ok()   { pass=$((pass+1)); echo "  ok   $1"; }
bad()  { failn=$((failn+1)); echo "  FAIL $1"; }
chk()  { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
newdb(){ $P -d postgres -c "DROP DATABASE IF EXISTS $1" -c "CREATE DATABASE $1 ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'" >/dev/null; DB=$1; }
q()    { psql -X -At -d "$DB" -c "$1" 2>&1; }
ap()   { $P -d "$DB" -1 -f "$SQL/$1" 2>&1; }                      # apply one file, one transaction
seeds(){ ap 998_dev_seed_auth.sql >/dev/null && ap 999_dev_seed.sql >/dev/null; }   # runner order, stops at first failure
base() { ap 001_initial_mvp.sql >/dev/null && ap 002_harden_mvp.sql >/dev/null; }
TABLES="organizations roles users customers product_categories units products product_specification_templates product_specification_fields product_specification_values purchase_requests purchase_request_items audit_logs refresh_tokens"
snap() { for t in $TABLES; do q "select '$t', count(*), md5(coalesce(string_agg(x::text,'|' order by x::text),'')) from $t x"; done | md5sum | cut -c1-12; }
counts(){ q "select (select count(*) from organizations),(select count(*) from roles),(select count(*) from units),(select count(*) from product_categories),(select count(*) from products),(select count(*) from customers),(select count(*) from product_specification_templates),(select count(*) from product_specification_fields),(select count(*) from product_specification_values),(select count(*) from users)"; }
EXPECT_DEMO="1|3|4|1|1|1|1|3|1|3"

echo "== A. empty database: 001,002,003, seeds 998+999 twice"
newdb tf_s01_a; base; ap 003_org_code_and_username.sql >/dev/null; seeds; c1=$(counts); s1=$(snap); seeds; chk "A1 counts after first run" "$c1" "$EXPECT_DEMO"; chk "A2 second run changes nothing" "$(snap)" "$s1"
chk "A3 org code DEMO" "$(q "select code from organizations")" "DEMO"
chk "A4 admin hash is argon2id" "$(q "select left(password_hash,30) from users where username='admin'")" '$argon2id$v=19$m=65536,t=3,p=4'
hs=$(q "select username||' '||password_hash from users order by username")
v=$(python3 -I - "$TOOLS" <<PY
import sys; sys.path.insert(0,sys.argv[1]); import mkhash
rows=[l.split(' ',1) for l in """$hs""".strip().splitlines()]
print(all(mkhash.verify('TradeFlow-Dev-1!',h) and not mkhash.verify('wrong',h) for u,h in rows), len(rows))
PY
); chk "A5 all 3 dev users verify with the dev password (argon2id recomputed)" "$v" "True 3"
chk "A6 dev users per role" "$(q "select string_agg(u.username||':'||r.code,',' order by u.username) from users u join roles r on r.id=u.role_id")" "accounting:ACCOUNTING,admin:ADMIN,sales:SALES"
chk "A7 spec value is valid option" "$(q "select value_option from product_specification_values")" "2"

echo "== B. legacy: 001,002, OLD 999 seeds, two real orgs, THEN 003, then 998/999 twice"
newdb tf_s01_b; base; ap 999_dev_seed.sql >/dev/null
q "insert into organizations(name,national_id,created_at) values ('Beta Steel','B-1','2030-01-01'),('Alpha Steel','A-1','2020-01-01')" >/dev/null
chk "B0 old seed left placeholder hash" "$(q "select password_hash from users where username='admin'")" "TEMPORARY_PASSWORD_HASH"
ap 003_org_code_and_username.sql >/dev/null
chk "B1 backfill" "$(q "select string_agg(name||'='||code,',' order by name) from organizations")" "Alpha Steel=ORG-000001,Beta Steel=ORG-000002,TradeFlow Demo=DEMO"
seeds; chk "B2 admin hash upgraded" "$(q "select left(password_hash,9) from users where username='admin'")" '$argon2id'
chk "B3 no duplicate demo data (org count 3, demo counts)" "$(q "select count(*) from organizations")|$(q "select count(*) from users")|$(q "select count(*) from roles")|$(q "select count(*) from units")" "3|3|3|4"
s1=$(snap); seeds; chk "B4 rerun changes nothing" "$(snap)" "$s1"
chk "B5 old customer/product kept (no duplicates)" "$(q "select (select count(*) from customers),(select count(*) from products)")" "1|1"

echo "== C. admin password changed must survive (fresh and legacy)"
q "update users set password_hash='CHANGED-BY-ADMIN' where username='admin'" >/dev/null; seeds; seeds
chk "C1 survives re-seeding (fresh path)" "$(q "select password_hash from users where username='admin'")" "CHANGED-BY-ADMIN"
newdb tf_s01_c2; base; ap 999_dev_seed.sql >/dev/null; q "update users set password_hash='LEGACY-CHANGED' where username='admin'" >/dev/null
ap 003_org_code_and_username.sql >/dev/null; seeds; seeds
chk "C2 survives 003 + 998 + 999 (legacy path)" "$(q "select password_hash from users where username='admin'")" "LEGACY-CHANGED"

echo "== D. same-name guard (4): real org named 'TradeFlow Demo', other national_id"
newdb tf_s01_d; base
q "insert into organizations(name,national_id) values ('TradeFlow Demo','REAL-001')" >/dev/null
q "insert into roles(organization_id,code,name) select id,'ADMIN','Admin' from organizations" >/dev/null
q "insert into users(organization_id,role_id,first_name,last_name,username,password_hash) select o.id,r.id,'R','L','real','realhash' from organizations o join roles r on r.organization_id=o.id" >/dev/null
ap 003_org_code_and_username.sql >/dev/null
chk "D0 real org was NOT given DEMO" "$(q "select code from organizations")" "ORG-000001"
b=$(snap); out=$(ap 998_dev_seed_auth.sql); rc=$?
echo "$out" | grep -q "not the demo organization" && ok "D1 998 aborts with the clear error" || bad "D1 message: $out"
chk "D2 real org + attached rows unchanged" "$(snap)" "$b"
chk "D3 no sample data anywhere" "$(q "select (select count(*) from units)+(select count(*) from products)+(select count(*) from customers)+(select count(*) from product_categories)")" "0"
seeds >/dev/null 2>&1; rc=$?; [ $rc -ne 0 ] && ok "D4 seed step fails as a whole -> runner would stop, 999 never runs" || bad "D4 seeds succeeded"
chk "D5 still unchanged after the seed step" "$(snap)" "$b"
echo "== D'. (5) real same-name org AND a proper demo org"
q "insert into organizations(name,national_id,code) values ('TradeFlow Demo','DEMO-NATIONAL-ID','DEMO')" >/dev/null
b=$(snap); ap 998_dev_seed_auth.sql 2>&1 | grep -q "organizations are named" && ok "D6 aborts (several share the name)" || bad "D6"
chk "D7 nothing changed" "$(snap)" "$b"
echo "== D''. demo org with a wrong code (reviewer control)"
newdb tf_s01_d2; base; ap 003_org_code_and_username.sql >/dev/null
q "insert into organizations(name,national_id,code) values ('TradeFlow Demo','DEMO-NATIONAL-ID','OTHER')" >/dev/null
b=$(snap); ap 998_dev_seed_auth.sql 2>&1 | grep -q "expected DEMO" && ok "D8 aborts, does not touch the immutable code" || bad "D8"
chk "D9 unchanged" "$(snap)" "$b"

echo "== E. 003 constraints"
newdb tf_s01_e; base; ap 003_org_code_and_username.sql >/dev/null
q "insert into organizations(name,code) values ('X','ORG-001')" >/dev/null
st() { psql -X -At -d "$DB" -c "\\set VERBOSITY verbose" -c "$1" 2>&1 | grep -o -E "ERROR:  [0-9A-Z]{5}" | head -1; }
chk "E1 duplicate code -> 23505"          "$(st "insert into organizations(name,code) values ('Y','ORG-001')")" "ERROR:  23505"
chk "E2 'org-001' (lower-case) -> 23514"  "$(st "insert into organizations(name,code) values ('Y','org-001')")" "ERROR:  23514"
chk "E3 ' ORG-002' (space) -> 23514"      "$(st "insert into organizations(name,code) values ('Y',' ORG-002')")" "ERROR:  23514"
chk "E4 one-char code -> 23514"           "$(st "insert into organizations(name,code) values ('Y','A')")" "ERROR:  23514"
chk "E5 leading dash -> 23514"            "$(st "insert into organizations(name,code) values ('Y','-AB')")" "ERROR:  23514"
chk "E6 51 chars -> 22001 or 23514"       "$(st "insert into organizations(name,code) values ('Y',repeat('A',51))" | sed 's/22001/23514/')" "ERROR:  23514"
chk "E7 NULL code -> 23502"               "$(st "insert into organizations(name) values ('Y')")" "ERROR:  23502"
chk "E8 code update -> 55000"             "$(st "update organizations set code='ORG-777' where code='ORG-001'")" "ERROR:  55000"
chk "E9 same-value code update allowed"   "$(q "update organizations set code='ORG-001' where code='ORG-001'")" "UPDATE 1"
chk "E10 other column update allowed"     "$(q "update organizations set name='X2' where code='ORG-001'")" "UPDATE 1"
oid=$(q "select id from organizations limit 1" | head -1)
q "insert into roles(organization_id,code,name) values ('$oid','ADMIN','A')" >/dev/null; rid=$(q "select id from roles limit 1" | head -1)
ins() { st "insert into users(organization_id,role_id,first_name,last_name,username,password_hash) values ('$oid','$rid','a','b','$1','h')"; }
chk "E11 username 'Admin' -> 23514" "$(ins Admin)" "ERROR:  23514"
chk "E12 username ' admin' -> 23514" "$(ins ' admin')" "ERROR:  23514"
chk "E13 username 'admin ' -> 23514" "$(ins 'admin ')" "ERROR:  23514"
chk "E14 username 'admin' ok" "$(ins admin)" ""
chk "E15 code is VARCHAR(50), unique index present" "$(q "select count(*) from pg_indexes where indexname='uq_organizations_code'")" "1"
chk "E16 trigger exists" "$(q "select count(*) from pg_trigger where tgname='trg_organizations_code_immutable'")" "1"

echo "== F. 003 fails loudly and atomically"
newdb tf_s01_f; base; ap 999_dev_seed.sql >/dev/null
q "insert into organizations(name,national_id) values ('TradeFlow Demo','DEMO-NATIONAL-ID')" >/dev/null   # 2nd row with the demo natural key
out=$(ap 003_org_code_and_username.sql); echo "$out" | grep -q "match the demo natural key" && ok "F1 duplicate demo key -> clear failure" || bad "F1: $out"
chk "F2 rolled back: no code column" "$(q "select count(*) from information_schema.columns where table_name='organizations' and column_name='code'")" "0"
newdb tf_s01_f2; base; ap 999_dev_seed.sql >/dev/null; q "update users set username='Admin'" >/dev/null
out=$(ap 003_org_code_and_username.sql); echo "$out" | grep -q "chk_users_username_normalized" && ok "F3 unnormalized username -> fails" || bad "F3: $out"
chk "F4 rolled back (no code column)" "$(q "select count(*) from information_schema.columns where table_name='organizations' and column_name='code'")" "0"
newdb tf_s01_f3; base; out=$(ap 003_org_code_and_username.sql; ap 003_org_code_and_username.sql); echo "$out" | grep -q "already exists" && ok "F5 re-applying 003 by hand fails (only the runner's version check protects it)" || bad "F5"

echo "== G. 002 regression + concurrency still pass on top of 003 (fixtures now supply organizations.code)"
newdb tf_s01_g; base; ap 003_org_code_and_username.sql >/dev/null
reg=$(psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -f "$HERE/regression_post003.sql" 2>&1); rc=$?
echo "$reg" | grep -E "^Passed" 
[ $rc -eq 0 ] && echo "$reg" | grep -Eq "^Passed [0-9]+ / Failed 0$" && ok "G1 regression_post003.sql: rc=0, Failed 0" || { bad "G1 regression (rc=$rc)"; echo "$reg" | tail -5; }
newdb tf_s01_g2; base; ap 003_org_code_and_username.sql >/dev/null
bash "$HERE/concurrency_post003.sh" tf_s01_g2 > /tmp/tf_s01_conc.out 2>&1
grep -q "duplicates=0" /tmp/tf_s01_conc.out && grep -q "last_number=500" /tmp/tf_s01_conc.out && grep -q "errors: 0" /tmp/tf_s01_conc.out && ok "G2 concurrency: 500 unique numbers, 0 errors" || { bad "G2 concurrency"; tail -5 /tmp/tf_s01_conc.out; }

echo; echo "passed=$pass failed=$failn"; [ $failn -eq 0 ]
