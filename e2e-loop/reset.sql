-- Reset do loop e2e: apaga TODOS os dados de teste da loja 'teste'.
-- Guarda: loja_id vem do slug 'teste'; aborta se nao existir. Mantem cadastro
-- (fila_vendedor, canais, agente_config, credenciais) e projecoes operacionais.
DO $$
DECLARE
  v_loja TEXT;
  -- Cliente do loop, normalizado sem o 9 (e como a Meta entrega o `from`).
  -- Ele tambem esta na fila_vendedor, entao precisa ficar de FORA da guarda
  -- de janela abaixo: preservado, o reset viraria no-op justo na conversa que
  -- todo cenario zera, e T1..T11 rodariam sobre historico velho.
  v_cliente TEXT := '555180336365';
BEGIN
  SELECT id INTO v_loja FROM lojas WHERE slug = 'teste';
  IF v_loja IS NULL THEN
    RAISE EXCEPTION 'loja teste inexistente, reset abortado';
  END IF;

  -- A janela de 24h da Meta e estado temporal (um "oi" real do vendedor),
  -- nao residuo de teste: sem ela, toda oferta cai no template pago e o T8
  -- nunca exercita a interativa. Preserva inbound do vendedor (com/sem 9),
  -- menos o do cliente do loop, que abre a propria janela a cada cenario.
  DELETE FROM mensagens WHERE loja_id = v_loja AND conversa_id NOT IN (
    SELECT c.id FROM conversas c JOIN fila_vendedor f
      ON f.loja_id = v_loja
      AND regexp_replace(regexp_replace(f.telefone, '\D', '', 'g'), '^(55\d{2})9(\d{8})$', '\1\2')
        <> v_cliente
      AND regexp_replace(regexp_replace(c.telefone, '\D', '', 'g'), '^(55\d{2})9(\d{8})$', '\1\2')
        = regexp_replace(regexp_replace(f.telefone, '\D', '', 'g'), '^(55\d{2})9(\d{8})$', '\1\2')
  );
  DELETE FROM conversas WHERE loja_id = v_loja AND id NOT IN (
    SELECT c.id FROM conversas c JOIN fila_vendedor f
      ON f.loja_id = v_loja
      AND regexp_replace(regexp_replace(f.telefone, '\D', '', 'g'), '^(55\d{2})9(\d{8})$', '\1\2')
        <> v_cliente
      AND regexp_replace(regexp_replace(c.telefone, '\D', '', 'g'), '^(55\d{2})9(\d{8})$', '\1\2')
        = regexp_replace(regexp_replace(f.telefone, '\D', '', 'g'), '^(55\d{2})9(\d{8})$', '\1\2')
  );
  DELETE FROM leads WHERE loja_id = v_loja;
  DELETE FROM consentimentos WHERE loja_id = v_loja;
  DELETE FROM oferta_lead WHERE loja_id = v_loja;
  DELETE FROM notificacoes_operacionais WHERE loja_id = v_loja;
  DELETE FROM ctwa_auditoria WHERE loja_id = v_loja;
  DELETE FROM catalog_attributions WHERE loja_id = v_loja;
  UPDATE rodizio_ponteiro SET posicao = 0 WHERE loja_id = v_loja;

  RAISE NOTICE 'reset ok na loja teste';
END $$;
