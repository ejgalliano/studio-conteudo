# 📱 Sistema de Conteúdo Estratégico — Como Usar

## Para cada cliente novo, siga estes 3 passos:

### PASSO 1 — Crie a pasta do cliente
Dentro de `_clientes/`, crie uma pasta com o nome do cliente.
Exemplo: `_clientes/JOAO-PADARIA/`

### PASSO 2 — Coloque os arquivos de input
Dentro da pasta do cliente, coloque dois arquivos:

**`transcricao.txt`** → Cole aqui o texto da transcrição do Tactiq (copie e cole, salve como .txt)

**`objetivos.txt`** → Escreva aqui os objetivos do cliente. Use este modelo:
```
# Objetivos — [Nome do Cliente]

## Objetivo Principal
[descreva o objetivo central]

## Objetivos Específicos
1. ...
2. ...

## Investimento em Mídia Paga
[valor e distribuição]

## Campanhas Prioritárias
[o que vai ao ar primeiro]

## Restrições e Preferências
[o que NÃO fazer]

## Tom de Voz
[como a marca deve soar]
```

### PASSO 3 — Abra o terminal na pasta do sistema e execute

1. Abra o PowerShell
2. Navegue até a pasta:
```
cd C:\Users\SeuNome\Documents\sistema-conteudo
```
3. Abra o Claude Code:
```
claude
```
4. Digite o comando:
```
execute o fluxo completo para o cliente [NOME-DA-PASTA]
```
Exemplo:
```
execute o fluxo completo para o cliente ARLEI-GARCIA
```

### O que vai acontecer
O Claude vai executar automaticamente todas as etapas e gerar os seguintes arquivos em `_outputs/[NOME]/`:

| Arquivo | Conteúdo |
|---|---|
| `00-DOCUMENTO-FINAL.md` | Tudo consolidado em um só lugar |
| `01-mapa-empatia.md` | Mapa de Empatia completo |
| `02-proposta-valor.md` | Proposta de Valor e diferenciais |
| `03-personas.md` | 3 a 5 personas detalhadas |
| `04-lista-temas.md` | 200 a 300 temas organizados por pilar |
| `05-conteudos.md` | 30+ legendas prontas para publicação |

---

## Dicas importantes

- **Não interrompa o processo** enquanto o Claude estiver executando
- Se algo sair errado, diga: `refaça a etapa [número]`
- Para ajustar um conteúdo específico, diga: `ajuste o conteúdo #[número] para [instrução]`
- Para adicionar mais conteúdos, diga: `crie mais 10 conteúdos de Reels para o cliente [NOME]`

---

## Clientes já processados
- ✅ ARLEI-GARCIA (corretor imobiliário, São Paulo)
