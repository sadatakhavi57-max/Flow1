-- TradeFlow regression suite (behavioural, not structural).
-- Runs against a database that already has the migrations applied.  Everything happens inside one
-- transaction that is rolled back, so it is safe to re-run.
--   psql -X -q -v ON_ERROR_STOP=1 -d <db> -f regression.sql      (exit code 3 when any assertion fails)
--
-- Convention: expect_ok = statement must succeed; expect_fail = statement must be rejected with an
-- error matching the pattern (a statement that is wrongly ACCEPTED is rolled back so later tests
-- still see a clean state).

\set QUIET on
SET client_min_messages = warning;
BEGIN;

CREATE TEMP TABLE results (n serial, area text, label text, ok boolean, detail text);

CREATE FUNCTION pg_temp.expect_ok(p_area text, p_label text, p_stmt text) RETURNS void
LANGUAGE plpgsql AS $f$
BEGIN
  BEGIN
    EXECUTE p_stmt;
    INSERT INTO results(area,label,ok,detail) VALUES (p_area, p_label, true, null);
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO results(area,label,ok,detail) VALUES (p_area, p_label, false, 'unexpectedly rejected: ' || SQLERRM);
  END;
END $f$;

CREATE FUNCTION pg_temp.expect_fail(p_area text, p_label text, p_stmt text, p_pattern text) RETURNS void
LANGUAGE plpgsql AS $f$
DECLARE v_err text; v_state text;
BEGIN
  BEGIN
    BEGIN
      EXECUTE p_stmt;
      RAISE EXCEPTION 'accepted' USING ERRCODE = 'TF999';   -- roll the accepted statement back
    EXCEPTION WHEN OTHERS THEN
      v_err := SQLERRM; v_state := SQLSTATE;
    END;
    IF v_state = 'TF999' THEN
      INSERT INTO results(area,label,ok,detail) VALUES (p_area, p_label, false, 'statement was ACCEPTED but must be rejected');
    ELSIF v_err ILIKE p_pattern THEN
      INSERT INTO results(area,label,ok,detail) VALUES (p_area, p_label, true, null);
    ELSE
      INSERT INTO results(area,label,ok,detail) VALUES (p_area, p_label, false, 'rejected, but with unexpected error: ' || v_err);
    END IF;
  END;
END $f$;

CREATE FUNCTION pg_temp.check_true(p_area text, p_label text, p_cond boolean, p_detail text DEFAULT NULL) RETURNS void
LANGUAGE plpgsql AS $f$
BEGIN
  INSERT INTO results(area,label,ok,detail) VALUES (p_area, p_label, coalesce(p_cond,false), CASE WHEN coalesce(p_cond,false) THEN NULL ELSE p_detail END);
END $f$;

-- run a scalar query, return its text value or 'ERROR: ...'
CREATE FUNCTION pg_temp.val(p_sql text) RETURNS text LANGUAGE plpgsql AS $f$
DECLARE v text;
BEGIN
  EXECUTE p_sql INTO v;
  RETURN v;
EXCEPTION WHEN OTHERS THEN
  RETURN 'ERROR: ' || SQLERRM;
END $f$;

DO $test$
DECLARE
  oa uuid := gen_random_uuid();  ob uuid := gen_random_uuid();
  ra uuid := gen_random_uuid();  rb uuid := gen_random_uuid();
  ua uuid := gen_random_uuid();  ub uuid := gen_random_uuid();
  una uuid := gen_random_uuid(); unb uuid := gen_random_uuid();
  ca uuid := gen_random_uuid();  cb uuid := gen_random_uuid();
  pa uuid := gen_random_uuid();  pb uuid := gen_random_uuid();
  cust1 uuid := gen_random_uuid(); cust2 uuid := gen_random_uuid(); cust_b uuid := gen_random_uuid();
  tpl_a uuid := gen_random_uuid(); tpl_b uuid := gen_random_uuid();
  fa1 uuid := gen_random_uuid();  fa2 uuid := gen_random_uuid(); fb1 uuid := gen_random_uuid();
  r_draft uuid := gen_random_uuid(); r_draft2 uuid := gen_random_uuid();
  r_sub uuid := gen_random_uuid();   r_canc uuid := gen_random_uuid(); r_dates uuid := gen_random_uuid();
  i_draft uuid := gen_random_uuid(); i_sub uuid := gen_random_uuid(); i_canc uuid := gen_random_uuid();
  today_teh date := (now() AT TIME ZONE 'Asia/Tehran')::date;
  snap jsonb; v text; n1 bigint;
BEGIN
  -- ---------------------------------------------------------------- fixtures (two tenants)
  INSERT INTO organizations(id,name,code) VALUES (oa,'OrgA','ORG-A'),(ob,'OrgB','ORG-B');
  INSERT INTO roles(id,organization_id,code,name) VALUES (ra,oa,'ADMIN','a'),(rb,ob,'ADMIN','b');
  INSERT INTO users(id,organization_id,role_id,first_name,last_name,username,password_hash)
       VALUES (ua,oa,ra,'x','y','admin','h'),(ub,ob,rb,'x','y','admin','h');
  INSERT INTO units(id,organization_id,name,code,unit_type) VALUES (una,oa,'kg','KG','WEIGHT'),(unb,ob,'kg','KG','WEIGHT');
  INSERT INTO product_categories(id,organization_id,name,code) VALUES (ca,oa,'c','C'),(cb,ob,'c','C');
  INSERT INTO products(id,organization_id,category_id,name,code,default_unit_id)
       VALUES (pa,oa,ca,'pipe','P',una),(pb,ob,cb,'pipe','P',unb);
  INSERT INTO customers(id,organization_id,customer_type,name,national_id) VALUES (cust1,oa,'INDIVIDUAL','Mohammad Rezaei','0012345678');
  INSERT INTO customers(id,organization_id,customer_type,name,national_id) VALUES (cust2,oa,'COMPANY','A Second Customer','0099999999');
  INSERT INTO customers(id,organization_id,customer_type,name) VALUES (cust_b,ob,'COMPANY','B Customer');
  INSERT INTO product_specification_templates(id,organization_id,name,code) VALUES (tpl_a,oa,'t','T'),(tpl_b,ob,'t','T');
  INSERT INTO product_specification_fields(id,organization_id,template_id,name,code,data_type) VALUES
       (fa1,oa,tpl_a,'Diameter','DIAMETER','DECIMAL'),
       (fa2,oa,tpl_a,'Thickness','THICKNESS','DECIMAL'),
       (fb1,ob,tpl_b,'Diameter','DIAMETER','DECIMAL');

  INSERT INTO purchase_requests(id,organization_id,request_number,customer_id,created_by) VALUES
       (r_draft ,oa,'PR-DRAFT' ,cust1,ua), (r_draft2,oa,'PR-DRAFT2',cust1,ua),
       (r_sub   ,oa,'PR-SUB'   ,cust1,ua), (r_canc  ,oa,'PR-CANC'  ,cust1,ua), (r_dates,oa,'PR-DATES',cust1,ua);
  INSERT INTO purchase_request_items(id,organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total)
       VALUES (i_draft,oa,r_draft,pa,2,una,1000,2000), (i_sub,oa,r_sub,pa,1,una,5000,5000), (i_canc,oa,r_canc,pa,1,una,700,700);
  UPDATE purchase_requests SET status='SUBMITTED' WHERE id = r_sub;
  UPDATE purchase_requests SET status='CANCELLED' WHERE id = r_canc;

  -- ---------------------------------------------------------------- R1 rounding contract (PG side)
  PERFORM pg_temp.expect_ok  ('rounding','qty 0.5 x 125001 -> line_total 62501 (half-up) accepted',
     format($$INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total) VALUES (%L,%L,%L,0.5,%L,125001,62501)$$, oa,r_draft,pa,una));
  PERFORM pg_temp.expect_fail('rounding','same line with half-even result 62500 rejected',
     format($$INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total) VALUES (%L,%L,%L,0.5,%L,125001,62500)$$, oa,r_draft,pa,una),
     '%line_total_consistency%');
  PERFORM pg_temp.check_true('rounding','header totals equal sum of lines after item insert',
     (SELECT grand_total = (SELECT sum(line_total) FROM purchase_request_items WHERE purchase_request_id = r_draft) FROM purchase_requests WHERE id = r_draft));

  -- ---------------------------------------------------------------- R2 customer names
  PERFORM pg_temp.expect_ok('customers','two different people may share a name',
     format($$INSERT INTO customers(organization_id,customer_type,name,national_id) VALUES (%L,'INDIVIDUAL','Mohammad Rezaei','0087654321')$$, oa));
  PERFORM pg_temp.expect_ok('customers','third customer with same name and no identifiers',
     format($$INSERT INTO customers(organization_id,customer_type,name) VALUES (%L,'INDIVIDUAL','Mohammad Rezaei')$$, oa));

  -- ---------------------------------------------------------------- R3 identifier normalisation
  PERFORM pg_temp.expect_ok('identifiers','Persian-digit national_id accepted',
     format($$INSERT INTO customers(id,organization_id,customer_type,name,national_id) VALUES (gen_random_uuid(),%L,'INDIVIDUAL','N1','۱۲۳۴۵۶۷۸۹۰')$$, oa));
  PERFORM pg_temp.check_true('identifiers','...is stored as ASCII digits',
     EXISTS (SELECT 1 FROM customers WHERE organization_id = oa AND national_id = '1234567890'));
  PERFORM pg_temp.expect_fail('identifiers','ASCII duplicate of Persian-digit id rejected',
     format($$INSERT INTO customers(organization_id,customer_type,name,national_id) VALUES (%L,'INDIVIDUAL','N2','1234567890')$$, oa), '%uq_customers_org_national_id%');
  PERFORM pg_temp.expect_fail('identifiers','Arabic-Indic digits duplicate rejected',
     format($$INSERT INTO customers(organization_id,customer_type,name,national_id) VALUES (%L,'INDIVIDUAL','N3','١٢٣٤٥٦٧٨٩٠')$$, oa), '%uq_customers_org_national_id%');
  PERFORM pg_temp.expect_fail('identifiers','id with inner space duplicate rejected',
     format($$INSERT INTO customers(organization_id,customer_type,name,national_id) VALUES (%L,'INDIVIDUAL','N4','12345 67890')$$, oa), '%uq_customers_org_national_id%');
  PERFORM pg_temp.expect_fail('identifiers','id with ZWNJ duplicate rejected',
     format($$INSERT INTO customers(organization_id,customer_type,name,national_id) VALUES (%L,'INDIVIDUAL','N5',%L)$$, oa, '12345'||chr(8204)||'67890'), '%uq_customers_org_national_id%');
  PERFORM pg_temp.expect_ok('identifiers','empty-string ids become NULL, so two such customers coexist',
     format($$INSERT INTO customers(organization_id,customer_type,name,national_id,economic_code) VALUES (%L,'INDIVIDUAL','E1','',''),(%L,'INDIVIDUAL','E2','  ','')$$, oa, oa));
  PERFORM pg_temp.check_true('identifiers','...and are stored as NULL',
     (SELECT count(*) FROM customers WHERE organization_id = oa AND name IN ('E1','E2') AND national_id IS NULL AND economic_code IS NULL) = 2);
  PERFORM pg_temp.expect_ok('identifiers','Persian-digit economic_code accepted',
     format($$INSERT INTO customers(organization_id,customer_type,name,economic_code) VALUES (%L,'COMPANY','EC1','۴۱۱۱۲۲۳۳۴۴')$$, oa));
  PERFORM pg_temp.expect_fail('identifiers','ASCII duplicate economic_code rejected',
     format($$INSERT INTO customers(organization_id,customer_type,name,economic_code) VALUES (%L,'COMPANY','EC2','4111223344')$$, oa), '%uq_customers_org_economic_code%');
  PERFORM pg_temp.expect_ok('identifiers','same national_id in another organization is allowed',
     format($$INSERT INTO customers(organization_id,customer_type,name,national_id) VALUES (%L,'INDIVIDUAL','Other tenant','0012345678')$$, ob));
  PERFORM pg_temp.expect_fail('identifiers','UPDATE to a duplicate (Persian digits) rejected',
     format($$UPDATE customers SET national_id = '۰۰۱۲۳۴۵۶۷۸' WHERE name = 'E1' AND organization_id = %L$$, oa), '%uq_customers_org_national_id%');

  -- ---------------------------------------------------------------- R4 delivery date
  PERFORM pg_temp.check_true('delivery','requested_delivery_date is of type date',
     (SELECT data_type FROM information_schema.columns WHERE table_name='purchase_requests' AND column_name='requested_delivery_date') = 'date',
     'column type is ' || (SELECT data_type FROM information_schema.columns WHERE table_name='purchase_requests' AND column_name='requested_delivery_date'));
  PERFORM pg_temp.expect_ok  ('delivery','delivery date = today (Tehran) accepted',
     format($$UPDATE purchase_requests SET requested_delivery_date = %L WHERE id = %L$$, today_teh, r_dates));
  PERFORM pg_temp.expect_ok  ('delivery','delivery date = tomorrow accepted',
     format($$UPDATE purchase_requests SET requested_delivery_date = %L WHERE id = %L$$, today_teh + 1, r_dates));
  PERFORM pg_temp.expect_fail('delivery','delivery date = yesterday rejected',
     format($$UPDATE purchase_requests SET requested_delivery_date = %L WHERE id = %L$$, today_teh - 1, r_dates), '%delivery_date%');

  -- ---------------------------------------------------------------- R5 audit append-only
  PERFORM pg_temp.expect_ok  ('audit','INSERT allowed',
     format($$INSERT INTO audit_logs(organization_id,user_id,entity_type,action) VALUES (%L,%L,'X','CREATE')$$, oa, ua));
  PERFORM pg_temp.expect_fail('audit','UPDATE rejected', $$UPDATE audit_logs SET action = 'HACKED'$$, '%append-only%');
  PERFORM pg_temp.expect_fail('audit','DELETE rejected', $$DELETE FROM audit_logs$$, '%append-only%');
  PERFORM pg_temp.expect_fail('audit','TRUNCATE rejected', $$TRUNCATE audit_logs$$, '%append-only%');

  -- ---------------------------------------------------------------- R6 state machine and freeze
  PERFORM pg_temp.expect_ok  ('draft','item price editable in DRAFT',
     format($$UPDATE purchase_request_items SET unit_price = 1100, line_total = 2200 WHERE id = %L$$, i_draft));
  PERFORM pg_temp.check_true ('draft','...header totals follow the edit',
     (SELECT grand_total = (SELECT sum(line_total) FROM purchase_request_items WHERE purchase_request_id = r_draft) FROM purchase_requests WHERE id = r_draft));
  PERFORM pg_temp.expect_ok  ('draft','item deletable in DRAFT',
     format($$DELETE FROM purchase_request_items WHERE purchase_request_id = %L AND id <> %L$$, r_draft, i_draft));
  PERFORM pg_temp.expect_fail('draft','item cannot be moved to another request',
     format($$UPDATE purchase_request_items SET purchase_request_id = %L WHERE id = %L$$, r_draft2, i_draft), '%cannot be moved%');
  PERFORM pg_temp.expect_fail('draft','request_number is immutable even in DRAFT',
     format($$UPDATE purchase_requests SET request_number = 'PR-X' WHERE id = %L$$, r_draft), '%immutable%');
  PERFORM pg_temp.expect_fail('draft','organization_id is immutable',
     format($$UPDATE purchase_requests SET organization_id = %L WHERE id = %L$$, ob, r_draft), '%');

  PERFORM pg_temp.expect_fail('submitted','INSERT item rejected',
     format($$INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total) VALUES (%L,%L,%L,1,%L,1000,1000)$$, oa,r_sub,pa,una), '%frozen%');
  PERFORM pg_temp.expect_fail('submitted','UPDATE item price rejected',
     format($$UPDATE purchase_request_items SET unit_price = 1, line_total = 1 WHERE id = %L$$, i_sub), '%frozen%');
  PERFORM pg_temp.expect_fail('submitted','UPDATE item quantity rejected',
     format($$UPDATE purchase_request_items SET quantity = 9, line_total = 45000 WHERE id = %L$$, i_sub), '%frozen%');
  PERFORM pg_temp.expect_fail('submitted','DELETE item rejected',
     format($$DELETE FROM purchase_request_items WHERE id = %L$$, i_sub), '%frozen%');
  PERFORM pg_temp.expect_fail('submitted','change customer rejected',
     format($$UPDATE purchase_requests SET customer_id = %L WHERE id = %L$$, cust2, r_sub), '%frozen%');
  PERFORM pg_temp.expect_fail('submitted','change grand_total rejected',
     format($$UPDATE purchase_requests SET subtotal = 1, grand_total = 1 WHERE id = %L$$, r_sub), '%frozen%');
  PERFORM pg_temp.expect_fail('submitted','change delivery date rejected',
     format($$UPDATE purchase_requests SET requested_delivery_date = %L WHERE id = %L$$, today_teh + 30, r_sub), '%frozen%');
  PERFORM pg_temp.expect_ok  ('submitted','notes remain editable (contract: not commercial content)',
     format($$UPDATE purchase_requests SET notes = 'call customer' WHERE id = %L$$, r_sub));
  PERFORM pg_temp.expect_fail('submitted','SUBMITTED -> DRAFT rejected',
     format($$UPDATE purchase_requests SET status = 'DRAFT' WHERE id = %L$$, r_sub), '%illegal status transition%');
  PERFORM pg_temp.expect_fail('submitted','DELETE request rejected',
     format($$DELETE FROM purchase_requests WHERE id = %L$$, r_sub), '%cannot be deleted%');

  PERFORM pg_temp.expect_fail('cancelled','INSERT item into CANCELLED request rejected',
     format($$INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total) VALUES (%L,%L,%L,1,%L,1000,1000)$$, oa,r_canc,pa,una), '%frozen%');
  PERFORM pg_temp.expect_fail('cancelled','CANCELLED -> SUBMITTED rejected',
     format($$UPDATE purchase_requests SET status = 'SUBMITTED' WHERE id = %L$$, r_canc), '%illegal status transition%');
  PERFORM pg_temp.expect_fail('cancelled','CANCELLED -> DRAFT rejected',
     format($$UPDATE purchase_requests SET status = 'DRAFT' WHERE id = %L$$, r_canc), '%illegal status transition%');

  PERFORM pg_temp.expect_ok  ('lifecycle','DRAFT -> SUBMITTED allowed',
     format($$UPDATE purchase_requests SET status = 'SUBMITTED' WHERE id = %L$$, r_draft));
  PERFORM pg_temp.expect_ok  ('lifecycle','SUBMITTED -> CANCELLED allowed',
     format($$UPDATE purchase_requests SET status = 'CANCELLED' WHERE id = %L$$, r_draft));
  PERFORM pg_temp.expect_ok  ('lifecycle','empty DRAFT request may be deleted',
     format($$DELETE FROM purchase_requests WHERE id = %L$$, r_draft2));

  -- ---------------------------------------------------------------- R7 item specification snapshot
  -- fresh draft for these tests
  INSERT INTO purchase_requests(id,organization_id,request_number,customer_id,created_by) VALUES (r_draft2,oa,'PR-SPEC',cust1,ua);
  snap := jsonb_build_array(jsonb_build_object('field_id',fa1,'field_code','DIAMETER','field_name','Diameter','data_type','DECIMAL','value',4));
  PERFORM pg_temp.expect_ok  ('specs','valid snapshot accepted',
     format($$INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total,specifications) VALUES (%L,%L,%L,1,%L,1000,1000,%L::jsonb)$$, oa,r_draft2,pa,una,snap));
  PERFORM pg_temp.check_true ('specs','snapshot is stored on the item',
     pg_temp.val(format($$SELECT specifications->0->>'field_name' FROM purchase_request_items WHERE purchase_request_id = %L$$, r_draft2)) = 'Diameter',
     'got: ' || coalesce(pg_temp.val(format($$SELECT specifications->0->>'field_name' FROM purchase_request_items WHERE purchase_request_id = %L$$, r_draft2)),'NULL'));
  PERFORM pg_temp.expect_fail('specs','non-array rejected',
     format($$UPDATE purchase_request_items SET specifications = '{}'::jsonb WHERE purchase_request_id = %L$$, r_draft2), '%specifications_array%');
  PERFORM pg_temp.expect_fail('specs','element missing "value" rejected',
     format($$UPDATE purchase_request_items SET specifications = %L::jsonb WHERE purchase_request_id = %L$$,
            jsonb_build_array(jsonb_build_object('field_id',fa1,'field_code','DIAMETER','field_name','Diameter','data_type','DECIMAL')), r_draft2), '%snapshot element%');
  PERFORM pg_temp.expect_fail('specs','field of another organization rejected',
     format($$UPDATE purchase_request_items SET specifications = %L::jsonb WHERE purchase_request_id = %L$$,
            jsonb_build_array(jsonb_build_object('field_id',fb1,'field_code','DIAMETER','field_name','Diameter','data_type','DECIMAL','value',4)), r_draft2), '%unknown field%');
  PERFORM pg_temp.expect_fail('specs','wrong field_code rejected',
     format($$UPDATE purchase_request_items SET specifications = %L::jsonb WHERE purchase_request_id = %L$$,
            jsonb_build_array(jsonb_build_object('field_id',fa1,'field_code','DIAM','field_name','Diameter','data_type','DECIMAL','value',4)), r_draft2), '%unknown field%');
  PERFORM pg_temp.expect_fail('specs','duplicate field rejected',
     format($$UPDATE purchase_request_items SET specifications = %L::jsonb WHERE purchase_request_id = %L$$,
            snap || snap, r_draft2), '%more than once%');
  PERFORM pg_temp.expect_fail('specs','non-UUID field_id rejected',
     format($$UPDATE purchase_request_items SET specifications = %L::jsonb WHERE purchase_request_id = %L$$,
            jsonb_build_array(jsonb_build_object('field_id','nope','field_code','DIAMETER','field_name','Diameter','data_type','DECIMAL','value',4)), r_draft2), '%not a UUID%');
  -- history survives master-data changes
  UPDATE product_specification_fields SET name = 'Outer diameter', code = 'OD' WHERE id = fa1;
  PERFORM pg_temp.check_true ('specs','snapshot unchanged after the master field is renamed',
     pg_temp.val(format($$SELECT specifications->0->>'field_code' || '/' || (specifications->0->>'field_name') FROM purchase_request_items WHERE purchase_request_id = %L$$, r_draft2)) = 'DIAMETER/Diameter');
  PERFORM pg_temp.expect_ok  ('specs','editing another column of that item still works after the master rename',
     format($$UPDATE purchase_request_items SET quantity = 2, line_total = 2000 WHERE purchase_request_id = %L$$, r_draft2));

  -- ---------------------------------------------------------------- R8 tenant isolation (kept from 001)
  PERFORM pg_temp.expect_fail('tenant','item with a product of another organization rejected',
     format($$INSERT INTO purchase_request_items(organization_id,purchase_request_id,product_id,quantity,unit_id,unit_price,line_total) VALUES (%L,%L,%L,1,%L,1000,1000)$$, oa,r_draft2,pb,una), '%foreign key%');
  PERFORM pg_temp.expect_fail('tenant','request pointing at a customer of another organization rejected',
     format($$INSERT INTO purchase_requests(organization_id,request_number,customer_id,created_by) VALUES (%L,'PR-X',%L,%L)$$, oa, cust_b, ua), '%foreign key%');

  -- ---------------------------------------------------------------- R9 request number counters
  v := pg_temp.val(format($$SELECT next_request_number(%L,'1405')$$, oa));
  PERFORM pg_temp.check_true('counter','first number of (orgA,1405) is 1', v = '1', 'got: ' || coalesce(v,'NULL'));
  v := pg_temp.val(format($$SELECT next_request_number(%L,'1405')$$, oa));
  PERFORM pg_temp.check_true('counter','second number is 2', v = '2', 'got: ' || coalesce(v,'NULL'));
  v := pg_temp.val(format($$SELECT next_request_number(%L,'1405')$$, oa));
  PERFORM pg_temp.check_true('counter','third number is 3 (no gaps)', v = '3', 'got: ' || coalesce(v,'NULL'));
  PERFORM pg_temp.check_true('counter','series are independent',
     pg_temp.val(format($$SELECT next_request_number(%L,'1406')$$, oa)) = '1');
  PERFORM pg_temp.check_true('counter','organizations are independent',
     pg_temp.val(format($$SELECT next_request_number(%L,'1405')$$, ob)) = '1');
  PERFORM pg_temp.check_true('counter','last_number of (orgA,1405) equals number of calls made (3)',
     pg_temp.val(format($$SELECT last_number FROM organization_request_counters WHERE organization_id = %L AND series = '1405'$$, oa)) = '3');

  -- ---------------------------------------------------------------- R10 bookkeeping
  PERFORM pg_temp.check_true('migration','002 is registered in schema_migrations',
     EXISTS (SELECT 1 FROM schema_migrations WHERE version = '002'));
END
$test$;

\echo
SELECT n, area, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result, label, coalesce(detail,'') AS detail
FROM results ORDER BY n;

SELECT count(*) FILTER (WHERE ok)     AS passed,
       count(*) FILTER (WHERE NOT ok) AS failed
FROM results \gset
\echo Passed :passed / Failed :failed

DO $$
BEGIN
  IF (SELECT count(*) FROM pg_temp.results WHERE NOT ok) > 0 THEN
    RAISE EXCEPTION 'REGRESSION FAILURES: %', (SELECT count(*) FROM pg_temp.results WHERE NOT ok);
  END IF;
END $$;

ROLLBACK;
