#!/usr/bin/env bash
# Concurrency checks against a database that has 001+002 applied (a throw-away DB: it commits data).
# Usage: PGHOST=... PGPORT=... PGUSER=... ./concurrency.sh <dbname>
set -u
DB=${1:?db name}
Q="psql -X -q -At -v ON_ERROR_STOP=1 -d $DB"
O=00000000-0000-0000-0000-00000000c0a1

$Q <<SQL
INSERT INTO organizations(id,name,code) VALUES ('$O','ConcOrg','CONC');
INSERT INTO roles(id,organization_id,code,name) VALUES ('00000000-0000-0000-0000-00000000c0a2','$O','ADMIN','r');
INSERT INTO users(id,organization_id,role_id,first_name,last_name,username,password_hash)
  VALUES ('00000000-0000-0000-0000-00000000c0a3','$O','00000000-0000-0000-0000-00000000c0a2','x','y','u','h');
INSERT INTO units(id,organization_id,name,code,unit_type) VALUES ('00000000-0000-0000-0000-00000000c0a4','$O','kg','KG','WEIGHT');
INSERT INTO product_categories(id,organization_id,name,code) VALUES ('00000000-0000-0000-0000-00000000c0a5','$O','c','C');
INSERT INTO products(id,organization_id,category_id,name,code,default_unit_id)
  VALUES ('00000000-0000-0000-0000-00000000c0a6','$O','00000000-0000-0000-0000-00000000c0a5','p','P','00000000-0000-0000-0000-00000000c0a4');
INSERT INTO customers(id,organization_id,customer_type,name) VALUES ('00000000-0000-0000-0000-00000000c0a7','$O','COMPANY','c');
INSERT INTO purchase_requests(id,organization_id,request_number,customer_id,created_by)
  VALUES ('00000000-0000-0000-0000-00000000c0a8','$O','PR-CONC','00000000-0000-0000-0000-00000000c0a7','00000000-0000-0000-0000-00000000c0a3');
SQL

echo "== T1  request-number counter: 20 sessions x 25 calls, each call its own transaction"
rm -f /tmp/cnt.*.out
for w in $(seq 1 20); do
  ( for i in $(seq 1 25); do echo "SELECT next_request_number('$O','C1');"; done | $Q -f - > /tmp/cnt.$w.out 2>&1 ) &
done; wait
cat /tmp/cnt.*.out | grep -c '^[0-9]' | sed 's/^/   numbers returned: /'
cat /tmp/cnt.*.out | grep -v '^[0-9]' | sort | uniq -c | sed 's/^/   non-numeric output: /'
cat /tmp/cnt.*.out | grep '^[0-9]' | sort -n | awk 'NR==1{min=$1} {if($1==prev) dup++; prev=$1; max=$1} END{printf "   min=%d max=%d duplicates=%d\n", min, max, dup+0}'
$Q -c "SELECT '   counter row last_number=' || last_number FROM organization_request_counters WHERE organization_id='$O' AND series='C1'"

echo "== T2  12 sessions x 10 item inserts into the SAME draft (deadlock check on the new guard trigger)"
rm -f /tmp/ins.*.out
for w in $(seq 1 12); do
  ( for i in $(seq 1 10); do
      echo "INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total) VALUES ('$O','00000000-0000-0000-0000-00000000c0a8','00000000-0000-0000-0000-00000000c0a6',1,'00000000-0000-0000-0000-00000000c0a4',1000,1000);"
    done | $Q -f - > /tmp/ins.$w.out 2>&1 ) &
done; wait
echo "   errors: $(cat /tmp/ins.*.out | grep -ci -E 'error|deadlock')"
$Q -c "SELECT '   items=' || (SELECT count(*) FROM purchase_request_items WHERE purchase_request_id='00000000-0000-0000-0000-00000000c0a8') || '  header_grand_total=' || grand_total || '  (expected 120000)' FROM purchase_requests WHERE id='00000000-0000-0000-0000-00000000c0a8'"

echo "== T3  submit racing with inserts: 1 submitter + 4 inserters"
$Q -c "INSERT INTO purchase_requests(id,organization_id,request_number,customer_id,created_by) VALUES ('00000000-0000-0000-0000-00000000c0b8','$O','PR-RACE','00000000-0000-0000-0000-00000000c0a7','00000000-0000-0000-0000-00000000c0a3')"
R=00000000-0000-0000-0000-00000000c0b8
rm -f /tmp/race.*.out
for w in 1 2 3 4; do
  ( for i in $(seq 1 60); do
      echo "INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total) VALUES ('$O','$R','00000000-0000-0000-0000-00000000c0a6',1,'00000000-0000-0000-0000-00000000c0a4',500,500);"
    done | $Q -f - > /tmp/race.$w.out 2>&1 ) &
done
( sleep 0.15; $Q -c "UPDATE purchase_requests SET status='SUBMITTED' WHERE id='$R'" > /tmp/race.submit.out 2>&1 ) &
wait
echo "   inserters stopped by the freeze: $(cat /tmp/race.[1-4].out | grep -c 'items are frozen') of 4   other errors/deadlocks: $(cat /tmp/race.*.out | grep -i -E 'error|deadlock' | grep -vc 'items are frozen')"
$Q -c "SELECT '   status=' || status || ' items=' || (SELECT count(*) FROM purchase_request_items WHERE purchase_request_id='$R') || ' header_grand_total=' || grand_total || ' sum_of_lines=' || (SELECT coalesce(sum(line_total),0) FROM purchase_request_items WHERE purchase_request_id='$R') FROM purchase_requests WHERE id='$R'"
