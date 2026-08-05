from app.servico import extrair_cpf, mascarar_cpf

# CPF válido usado nos testes (dígitos verificadores conferem): 111.444.777-35
CPF_FMT = "111.444.777-35"
CPF_BARE = "11144477735"


def test_mascara_cpf_formatado():
    assert mascarar_cpf(CPF_FMT) == "***.***.***-35"


def test_mascara_cpf_avulso_valido():
    assert mascarar_cpf(CPF_BARE) == "*********35"


def test_nao_mascara_11_digitos_invalidos():
    # sequência de 11 dígitos que não passa no dígito verificador (ex.: telefone)
    assert mascarar_cpf("11987654321") == "11987654321"


def test_nao_mascara_telefone_com_ddi():
    # 13 dígitos não são CPF e não devem ser tocados
    assert mascarar_cpf("5511988887777") == "5511988887777"


def test_mascara_cpf_no_meio_da_frase():
    texto = "Segue meu CPF 111.444.777-35 para a simulação, obrigado."
    assert mascarar_cpf(texto) == "Segue meu CPF ***.***.***-35 para a simulação, obrigado."


def test_mascara_cpf_avulso_no_meio_da_frase():
    assert mascarar_cpf("cpf 11144477735 fim") == "cpf *********35 fim"


def test_nao_mangla_sequencia_mais_longa():
    # não deve mascarar um trecho de 11 dígitos dentro de um número maior
    assert mascarar_cpf("111444777350000") == "111444777350000"


def test_texto_vazio_ou_none():
    assert mascarar_cpf("") == ""
    assert mascarar_cpf(None) is None


def test_extrair_cpf_formatado_e_avulso():
    assert extrair_cpf(CPF_FMT) == CPF_BARE
    assert extrair_cpf(f"meu cpf {CPF_BARE} ok") == CPF_BARE
    assert extrair_cpf(f"CPF: {CPF_FMT}") == CPF_BARE


def test_extrair_cpf_ignora_mascarado_e_invalido():
    assert extrair_cpf("*********35") is None
    assert extrair_cpf("***.***.***-35") is None
    assert extrair_cpf("11987654321") is None
    assert extrair_cpf("") is None
    assert extrair_cpf(None) is None
