-- ============================================================
-- snowflake/sql/rbac_and_masking.sql
-- RetailGuard — Governança e Segurança Snowflake
-- ------------------------------------------------------------
-- PROPÓSITO
--   B1) RBAC de menor privilégio (least privilege) para o dashboard
--       Streamlit-in-Snowflake (RETAIL_DB.PUBLIC.RETAIL_DASHBOARD):
--       cria a role RETAIL_DASHBOARD_ROLE com APENAS os GRANTs que o
--       app realmente usa (3 tabelas RAW + todas as MARTS).
--   B2) Dynamic Data Masking sobre PII em RETAIL_DB.RAW.CUSTOMERS,
--       liberando o valor em claro só para ACCOUNTADMIN e para a role
--       de governança RETAIL_GOVERNANCE_ROLE.
--
--   Script IDEMPOTENTE: pode ser re-executado sem erro
--   (CREATE ... IF NOT EXISTS / CREATE MASKING POLICY IF NOT EXISTS /
--    ALTER ... SET MASKING POLICY é declarativo por coluna).
--
--   SEGURANÇA: este arquivo NÃO contém senhas e NÃO cria usuários.
--   Credenciais do Snowflake vêm de env vars / connection 'retail'.
--
-- ------------------------------------------------------------
-- COMO RODAR
--   snow sql -c retail -f snowflake/sql/rbac_and_masking.sql
--
--   (Executar como ACCOUNTADMIN ou role com privilégio de criar roles,
--    masking policies e de fazer GRANT nos objetos abaixo.)
--
-- ------------------------------------------------------------
-- COMO TESTAR
--   Ver o bloco "TESTES" comentado no fim do arquivo. Resumo:
--     -- como role privilegiada (vê PII em claro):
--     USE ROLE RETAIL_GOVERNANCE_ROLE;
--     SELECT customer_id, first_name, email, phone, nif
--       FROM RETAIL_DB.RAW.CUSTOMERS LIMIT 5;
--     -- como role do dashboard (vê PII mascarada):
--     USE ROLE RETAIL_DASHBOARD_ROLE;
--     SELECT customer_id, first_name, email, phone, nif
--       FROM RETAIL_DB.RAW.CUSTOMERS LIMIT 5;
--
-- ------------------------------------------------------------
-- COMO REVERTER (rollback)
--   Ver o bloco "ROLLBACK" comentado no fim do arquivo:
--   UNSET das masking policies nas colunas, DROP das policies e
--   DROP das roles. Os comandos estão prontos, basta descomentar.
-- ============================================================

-- Roda como ACCOUNTADMIN (ou role com MANAGE GRANTS e CREATE ROLE).
USE ROLE ACCOUNTADMIN;
USE DATABASE RETAIL_DB;
USE WAREHOUSE COMPUTE_WH;


-- ============================================================
-- B1) RBAC — RETAIL_DASHBOARD_ROLE (menor privilégio)
-- ============================================================
-- A role do dashboard NÃO recebe ALL/OWNERSHIP em schema nenhum.
-- Recebe apenas USAGE (database/schemas/warehouse) e SELECT nas
-- tabelas que o streamlit_app.py de fato consulta.

CREATE ROLE IF NOT EXISTS RETAIL_DASHBOARD_ROLE
  COMMENT = 'Role de menor privilégio para o Streamlit RETAIL_DASHBOARD. SELECT só nas tabelas lidas pelo app.';

-- USAGE no database e nos schemas usados:
--   RAW    -> SALES, SALE_LINES, PRODUCTS (canônicas)
--   MARTS  -> todos os MART_*
--   PUBLIC -> onde o app Streamlit vive (RETAIL_DB.PUBLIC, ver snowflake.yml)
GRANT USAGE ON DATABASE RETAIL_DB                 TO ROLE RETAIL_DASHBOARD_ROLE;
GRANT USAGE ON SCHEMA   RETAIL_DB.RAW             TO ROLE RETAIL_DASHBOARD_ROLE;
GRANT USAGE ON SCHEMA   RETAIL_DB.MARTS           TO ROLE RETAIL_DASHBOARD_ROLE;
GRANT USAGE ON SCHEMA   RETAIL_DB.PUBLIC          TO ROLE RETAIL_DASHBOARD_ROLE;

-- Warehouse usado pelo app (query_warehouse: COMPUTE_WH em snowflake.yml).
-- USAGE permite rodar queries; OPERATE permite retomar/suspender (não é
-- necessário para um app que só lê, então NÃO concedemos OPERATE).
GRANT USAGE ON WAREHOUSE COMPUTE_WH               TO ROLE RETAIL_DASHBOARD_ROLE;

-- SELECT nas tabelas RAW canônicas (o dashboard lê MARTS; estas ficam
-- disponíveis para drill-down/diagnóstico ad-hoc no schema RAW).
GRANT SELECT ON TABLE RETAIL_DB.RAW.SALES       TO ROLE RETAIL_DASHBOARD_ROLE;
GRANT SELECT ON TABLE RETAIL_DB.RAW.SALE_LINES  TO ROLE RETAIL_DASHBOARD_ROLE;
GRANT SELECT ON TABLE RETAIL_DB.RAW.PRODUCTS    TO ROLE RETAIL_DASHBOARD_ROLE;

-- SELECT em TODAS as MARTS (atuais e futuras). O app consome vários
-- MART_* (GMV, MARGEM, CARRIER, RFM, CHURN, AP_AGING, IVA, etc.) e novos
-- marts criados pelo dbt continuarão acessíveis sem novo GRANT manual.
GRANT SELECT ON ALL TABLES    IN SCHEMA RETAIL_DB.MARTS TO ROLE RETAIL_DASHBOARD_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA RETAIL_DB.MARTS TO ROLE RETAIL_DASHBOARD_ROLE;
-- Alguns marts podem ser materializados como VIEW pelo dbt; cubra os dois casos.
GRANT SELECT ON ALL VIEWS     IN SCHEMA RETAIL_DB.MARTS TO ROLE RETAIL_DASHBOARD_ROLE;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA RETAIL_DB.MARTS TO ROLE RETAIL_DASHBOARD_ROLE;

-- Disponibiliza a role para quem administra (ajuste o grantee conforme
-- sua organização). ACCOUNTADMIN poder usar a role facilita os testes.
GRANT ROLE RETAIL_DASHBOARD_ROLE TO ROLE ACCOUNTADMIN;

-- ------------------------------------------------------------
-- (OPCIONAL / CONDICIONAL) Transferir OWNERSHIP do app Streamlit
-- para a RETAIL_DASHBOARD_ROLE.
--
-- POR QUÊ: hoje o app provavelmente pertence a ACCOUNTADMIN e roda no
-- "owner's rights" desse super-role. Transferir o ownership para a
-- RETAIL_DASHBOARD_ROLE faz o app rodar com APENAS os privilégios
-- concedidos acima — removendo a dependência de ACCOUNTADMIN e
-- garantindo o menor privilégio de verdade em runtime.
--
-- COPY CURRENT GRANTS preserva os grants já existentes no objeto durante
-- a transferência (evita "perder" acessos no momento da troca).
--
-- ATENÇÃO: TESTE ANTES em ambiente não-produtivo. Depois de transferir,
-- a role precisa enxergar TUDO que o app usa em runtime (as tabelas acima).
-- Se faltar algum GRANT, o app quebra. Por isso deixamos COMENTADO.
--
-- Pré-requisito: a role precisa de USAGE no schema do app (PUBLIC) — já
-- concedido acima. O nome do objeto vem de snowflake.yml (RETAIL_DASHBOARD).
--
-- GRANT OWNERSHIP ON STREAMLIT RETAIL_DB.PUBLIC.RETAIL_DASHBOARD
--   TO ROLE RETAIL_DASHBOARD_ROLE
--   COPY CURRENT GRANTS;
--
-- Para reverter o ownership de volta para ACCOUNTADMIN:
-- GRANT OWNERSHIP ON STREAMLIT RETAIL_DB.PUBLIC.RETAIL_DASHBOARD
--   TO ROLE ACCOUNTADMIN
--   COPY CURRENT GRANTS;
-- ------------------------------------------------------------


-- ============================================================
-- B2) DYNAMIC DATA MASKING — PII em RETAIL_DB.RAW.CUSTOMERS
-- ============================================================
-- Quem vê em CLARO: ACCOUNTADMIN e RETAIL_GOVERNANCE_ROLE.
-- Qualquer outra role (inclusive RETAIL_DASHBOARD_ROLE) vê mascarado.
--
-- Colunas PII alvo (todas VARCHAR em RAW.CUSTOMERS):
--   email, phone, nif (= tax_id ES), first_name, last_name, address_street
--
-- Usamos UMA policy por FORMATO de mascaramento, todas sobre VARCHAR.
-- O tipo da policy deve casar com o tipo da coluna (todas VARCHAR aqui).

-- Role que enxerga PII em claro (auditoria/compliance/governança).
CREATE ROLE IF NOT EXISTS RETAIL_GOVERNANCE_ROLE
  COMMENT = 'Role de governança: enxerga PII de CUSTOMERS em claro (bypass das masking policies).';
GRANT ROLE RETAIL_GOVERNANCE_ROLE TO ROLE ACCOUNTADMIN;

-- Para consultar a tabela em claro, a role de governança precisa de
-- USAGE + SELECT no objeto (independente do bypass de masking).
GRANT USAGE  ON DATABASE RETAIL_DB             TO ROLE RETAIL_GOVERNANCE_ROLE;
GRANT USAGE  ON SCHEMA   RETAIL_DB.RAW         TO ROLE RETAIL_GOVERNANCE_ROLE;
GRANT USAGE  ON WAREHOUSE COMPUTE_WH           TO ROLE RETAIL_GOVERNANCE_ROLE;
GRANT SELECT ON TABLE RETAIL_DB.RAW.CUSTOMERS  TO ROLE RETAIL_GOVERNANCE_ROLE;

-- ------------------------------------------------------------
-- Policy 1: EMAIL — mantém só o domínio (ex.: 'ana@gmail.com' -> '***@gmail.com')
-- ------------------------------------------------------------
CREATE MASKING POLICY IF NOT EXISTS RETAIL_DB.RAW.MASK_EMAIL
  AS (val STRING) RETURNS STRING ->
    CASE
      WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN','RETAIL_GOVERNANCE_ROLE')
        THEN val
      WHEN val IS NULL
        THEN NULL
      ELSE '***@' || COALESCE(NULLIF(SPLIT_PART(val, '@', 2), ''), '***')
    END
  COMMENT = 'Mascara e-mail: preserva apenas o domínio. Claro só p/ ACCOUNTADMIN e RETAIL_GOVERNANCE_ROLE.';

-- ------------------------------------------------------------
-- Policy 2: NIF (tax_id ES) — formato fixo redigido
-- ------------------------------------------------------------
CREATE MASKING POLICY IF NOT EXISTS RETAIL_DB.RAW.MASK_NIF
  AS (val STRING) RETURNS STRING ->
    CASE
      WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN','RETAIL_GOVERNANCE_ROLE')
        THEN val
      WHEN val IS NULL
        THEN NULL
      ELSE 'XXX****'
    END
  COMMENT = 'Mascara NIF/tax_id ES -> XXX****. Claro só p/ ACCOUNTADMIN e RETAIL_GOVERNANCE_ROLE.';

-- ------------------------------------------------------------
-- Policy 3: PHONE — redige o número inteiro
-- ------------------------------------------------------------
CREATE MASKING POLICY IF NOT EXISTS RETAIL_DB.RAW.MASK_PHONE
  AS (val STRING) RETURNS STRING ->
    CASE
      WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN','RETAIL_GOVERNANCE_ROLE')
        THEN val
      WHEN val IS NULL
        THEN NULL
      ELSE '***'
    END
  COMMENT = 'Mascara telefone -> ***. Claro só p/ ACCOUNTADMIN e RETAIL_GOVERNANCE_ROLE.';

-- ------------------------------------------------------------
-- Policy 4: NOME / ENDEREÇO (texto livre) — redige completamente
-- Reutilizável para first_name, last_name e address_street.
-- ------------------------------------------------------------
CREATE MASKING POLICY IF NOT EXISTS RETAIL_DB.RAW.MASK_TEXT_PII
  AS (val STRING) RETURNS STRING ->
    CASE
      WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN','RETAIL_GOVERNANCE_ROLE')
        THEN val
      WHEN val IS NULL
        THEN NULL
      ELSE '***'
    END
  COMMENT = 'Mascara texto PII (nomes, endereço) -> ***. Claro só p/ ACCOUNTADMIN e RETAIL_GOVERNANCE_ROLE.';

-- ------------------------------------------------------------
-- Aplica as policies às colunas de RETAIL_DB.RAW.CUSTOMERS.
-- ALTER ... SET MASKING POLICY é declarativo: re-rodar é seguro
-- (substitui a policy da coluna; mesma policy = no-op).
-- ------------------------------------------------------------
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS
  MODIFY COLUMN email          SET MASKING POLICY RETAIL_DB.RAW.MASK_EMAIL    FORCE;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS
  MODIFY COLUMN nif            SET MASKING POLICY RETAIL_DB.RAW.MASK_NIF      FORCE;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS
  MODIFY COLUMN phone          SET MASKING POLICY RETAIL_DB.RAW.MASK_PHONE    FORCE;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS
  MODIFY COLUMN first_name     SET MASKING POLICY RETAIL_DB.RAW.MASK_TEXT_PII FORCE;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS
  MODIFY COLUMN last_name      SET MASKING POLICY RETAIL_DB.RAW.MASK_TEXT_PII FORCE;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS
  MODIFY COLUMN address_street SET MASKING POLICY RETAIL_DB.RAW.MASK_TEXT_PII FORCE;

-- FORCE: substitui qualquer policy já aplicada à coluna sem precisar de
-- UNSET prévio, garantindo idempotência mesmo em re-execuções.


-- ============================================================
-- TESTES (executar manualmente — NÃO faz parte do deploy)
-- ============================================================
/*

-- 1) Como role de governança: PII em CLARO
USE ROLE RETAIL_GOVERNANCE_ROLE;
USE WAREHOUSE COMPUTE_WH;
SELECT customer_id, first_name, last_name, email, phone, nif, address_street
  FROM RETAIL_DB.RAW.CUSTOMERS
  LIMIT 5;
-- Esperado: valores reais (joão@..., +34..., 12345678Z, etc.)

-- 2) Como role do dashboard: PII MASCARADA
USE ROLE RETAIL_DASHBOARD_ROLE;
USE WAREHOUSE COMPUTE_WH;
-- (precisa de SELECT em CUSTOMERS p/ este teste; a role NÃO tem por padrão,
--  então conceda temporariamente só para validar o mascaramento:)
--   USE ROLE ACCOUNTADMIN;
--   GRANT SELECT ON TABLE RETAIL_DB.RAW.CUSTOMERS TO ROLE RETAIL_DASHBOARD_ROLE;
--   USE ROLE RETAIL_DASHBOARD_ROLE;
SELECT customer_id, first_name, last_name, email, phone, nif, address_street
  FROM RETAIL_DB.RAW.CUSTOMERS
  LIMIT 5;
-- Esperado: first_name='***', email='***@gmail.com', phone='***',
--           nif='XXX****', address_street='***'
-- Lembre de REVOGAR depois do teste (o app NÃO deve ler CUSTOMERS):
--   USE ROLE ACCOUNTADMIN;
--   REVOKE SELECT ON TABLE RETAIL_DB.RAW.CUSTOMERS FROM ROLE RETAIL_DASHBOARD_ROLE;

-- 3) Validar que o app enxerga o que precisa (RAW canônico + MARTS)
USE ROLE RETAIL_DASHBOARD_ROLE;
SELECT COUNT(*) FROM RETAIL_DB.RAW.SALES;
SELECT COUNT(*) FROM RETAIL_DB.RAW.SALE_LINES;
SELECT COUNT(*) FROM RETAIL_DB.RAW.PRODUCTS;
SELECT COUNT(*) FROM RETAIL_DB.MARTS.MART_GMV_MENSAL;

-- 4) Inspecionar onde cada policy está aplicada
USE ROLE ACCOUNTADMIN;
SELECT * FROM TABLE(
  RETAIL_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(
    REF_ENTITY_NAME => 'RETAIL_DB.RAW.CUSTOMERS',
    REF_ENTITY_DOMAIN => 'TABLE'
  )
);

*/


-- ============================================================
-- ROLLBACK (executar manualmente — NÃO faz parte do deploy)
-- ============================================================
/*

USE ROLE ACCOUNTADMIN;

-- 1) Remover as policies das colunas (precisa de UNSET antes de DROP)
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS MODIFY COLUMN email          UNSET MASKING POLICY;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS MODIFY COLUMN nif            UNSET MASKING POLICY;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS MODIFY COLUMN phone          UNSET MASKING POLICY;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS MODIFY COLUMN first_name     UNSET MASKING POLICY;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS MODIFY COLUMN last_name      UNSET MASKING POLICY;
ALTER TABLE RETAIL_DB.RAW.CUSTOMERS MODIFY COLUMN address_street UNSET MASKING POLICY;

-- 2) Dropar as masking policies
DROP MASKING POLICY IF EXISTS RETAIL_DB.RAW.MASK_EMAIL;
DROP MASKING POLICY IF EXISTS RETAIL_DB.RAW.MASK_NIF;
DROP MASKING POLICY IF EXISTS RETAIL_DB.RAW.MASK_PHONE;
DROP MASKING POLICY IF EXISTS RETAIL_DB.RAW.MASK_TEXT_PII;

-- 3) (Se transferiu o ownership do app) devolver para ACCOUNTADMIN — ver bloco B1.

-- 4) Dropar as roles (revoga implicitamente todos os grants associados)
DROP ROLE IF EXISTS RETAIL_DASHBOARD_ROLE;
DROP ROLE IF EXISTS RETAIL_GOVERNANCE_ROLE;

*/
-- ============================================================
-- FIM
-- ============================================================
