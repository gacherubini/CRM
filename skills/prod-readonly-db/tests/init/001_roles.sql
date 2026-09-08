-- Fixture exclusiva da suite de integracao: valores falsos, papeis falsos.
-- O usuario do init (postgres, superuser) e dono de tudo; as roles de teste
-- nao possuem nada, nao herdam nada e so leem o que e explicitamente liberado.

-- Revoga defaults inseguros para que o preflight da role segura volte limpo.
REVOKE ALL ON DATABASE fixturedb FROM PUBLIC;
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA reporting;
REVOKE ALL ON SCHEMA reporting FROM PUBLIC;

CREATE TABLE reporting.orders (
  id integer PRIMARY KEY,
  status text NOT NULL
);
INSERT INTO reporting.orders (id, status) VALUES
  (1, 'pending'),
  (2, 'paid'),
  (3, 'shipped');

-- Rotina de escrita: so existe para provar que a role segura nao pode
-- executa-la (o preflight recusa EXECUTE em rotina de usuario).
CREATE OR REPLACE FUNCTION reporting.unsafe_touch() RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO reporting.orders (id, status) VALUES (999, 'touched');
END;
$$;
REVOKE ALL ON FUNCTION reporting.unsafe_touch() FROM PUBLIC;

CREATE ROLE readonly_ok LOGIN PASSWORD 'integration-only'
  NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE readonly_bad LOGIN PASSWORD 'integration-only'
  NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

GRANT CONNECT ON DATABASE fixturedb TO readonly_ok, readonly_bad;
GRANT USAGE ON SCHEMA reporting TO readonly_ok, readonly_bad;
GRANT SELECT ON reporting.orders TO readonly_ok;
GRANT SELECT, INSERT ON reporting.orders TO readonly_bad;
GRANT EXECUTE ON FUNCTION reporting.unsafe_touch() TO readonly_bad;

-- O preflight exige default_transaction_read_only ligado na role.
ALTER ROLE readonly_ok SET default_transaction_read_only = on;
ALTER ROLE readonly_bad SET default_transaction_read_only = on;

-- Objetos futuros criados pelo dono seguem so-leitura para a role segura.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA reporting
  GRANT SELECT ON TABLES TO readonly_ok;
