#IR Ações Swing Trade 
import pandas as pd 
import numpy as np 
import matplotlib.pyplot as plt
import os
import re
import glob 
import datetime
import seaborn as sns
import pdb

#Diretório
os.chdir('C:/Users/Registros')


#1) Importação e ajustes da DataFrame:
swa = pd.read_csv('Operacoes.csv',
	sep = ';',
	decimal = '.',
	parse_dates = ['Data'],
	dayfirst = True,
	index_col = ['Título', 'Data'],
	encoding = 'latin-1')

#Ordena por Título (nome do ticker) e Data
swa.sort_index(inplace = True) 



#Primeiramente, redefine-se a coluna quantidade negociada. As vendas entraram com o valor negativo
negocios = [] 

for index, row in swa.iterrows():
	if row['C/V'] == 'Venda':
		negocios.append(row['Qtd_Negociada'] * -1)
	else:
		negocios.append(row['Qtd_Negociada'])

swa['Qtd_Negociada'] = negocios



#Algumas colunas complementares:
#Valor total por ação. Esse valor será utilizado ao calcular a taxa por ação: valor total das taxas ponderado pelo valor da operação. Por isso, mesmo nas vendas é preciso que o valor da operação seja positivo:
swa['Valor Operação'] = abs(swa['Qtd_Negociada']) * swa['Preço']


#Quando se compra mais de um título na mesma nota, as taxas devem ser divididas proporcionalmente ao valor de compra/venda de cada título. Abaixo, obteremos as proporções do valor de compra/venda de cada título no total da nota. Isso será feito criando uma outra df, que depois será unida com a swa: 
valor_bruto_nota = swa.groupby(['Título', 'Data', 'Nota'])['Valor Operação'].sum()
valor_proporcional_acao = valor_bruto_nota.groupby('Nota').apply(lambda x: x/ x.sum())
valor_proporcional_acao.name = 'Proporção'

#Juntando na base swa:
swt_acoes = pd.merge(left = swa, right = valor_proporcional_acao, how = 'left', on = ['Título', 'Data'])
swt_acoes['Taxa p/Ação'] = swt_acoes['Taxas por Nota'] * swt_acoes['Proporção'] 


#Para fins de IR: se estamos comprando, o valor líquido da operação é o Valor Bruto MAIS (e não menos) o Valor da Taxa por Ação! Porque esse valor será deduzido do IR! Se estamos vendendo o valor líquido da operação é o Valor Bruto MENOS o Valor da Taxa por Ação (isso é o mesmo que somar a taxa ao valor bruto se esse estiver negativo):
#Valor Líquido das Operações
swt_acoes['VLO'] = swt_acoes['Qtd_Negociada'] * swt_acoes['Preço'] + swt_acoes['Taxa p/Ação']
# Quantidade no portfólio:
swt_acoes['Quantidade'] = swt_acoes.groupby('Título')['Qtd_Negociada'].cumsum()
swt_acoes['Var_quant'] = swt_acoes.groupby('Título')['Quantidade'].pct_change()


#Aqui, para calcular o preço unitário. Automatizar o cálculo do preço médio ganha complexidade em situações em que há venda e recompra de ações, sem que elas tenham zero em algum momento (se tivessem zerado, o cálculo do preço médio recomeçaria a partir da nova compra). Por exemplo:
#1) Possui 500 ações a 21.40
#2) Vende-se 300 ações.
#3) Compra-se 400 ações a 18.70.

#O código abaixo garante que o preço médio seja obtido em quaisquer situações:
ativos = swt_acoes.groupby('Título')
vlt = []
for name, group in ativos:
	v_aux = 0 
	for index, row in group.iterrows():
		if row['C/V'] == 'Compra':
			v_aux += row['VLO']
		else:
			v_aux *= 1 + row['Var_quant']
		vlt.append(v_aux)

swt_acoes['VTO'] = vlt

#Preço Unitário:
swt_acoes['Preço Unitário'] = swt_acoes['VTO']/swt_acoes['Quantidade']
swt_acoes['Preço Unitário'].fillna(method = 'ffill', inplace = True)

#Lucro:
swt_acoes['Lucro'] = abs(swt_acoes['VLO']) - (swt_acoes['Preço Unitário']) * abs(swt_acoes['Qtd_Negociada'])

lcr = [] 
for index, row in swt_acoes.iterrows():
	if row['C/V'] == 'Venda':
		lcr.append(row['Lucro'])
	else:
		lcr.append(0)

swt_acoes['Resultado p/Ação'] = lcr

#Nas notas, já consta o IRRF. Eu criei uma coluna com o cálculo de operação para INTUITO DE COMPARAÇÃO:
irrf_calc = [] 
for index, row in swt_acoes.iterrows():
	if row['C/V'] == 'Venda':
		irrf_calc.append(row['Valor Operação'] * 0.00005)
	else:
		irrf_calc.append(0)

swt_acoes['IRRF_calculado'] = irrf_calc


#Tirar a coluna de lucro (porque ela foi feita somente para calcular o Resultado p/Ação)
swt_acoes.drop(['Lucro'], axis = 1, inplace = True)

colunas_print = ['Nota', 'Qtd_Negociada', 'C/V', 'Preço', 'Taxa p/Ação', 'Quantidade','VLO', 'Preço Unitário', 'Resultado p/Ação', 'IRRF por Nota', 'IRRF_calculado']
print("Essa é a DataFrame que contém as transações:\n", swt_acoes[colunas_print])


#O IR é calculado de acordo com o lucro de todas as ações no mês. O primeiro passo então é calcular o 
swt_acoes_month = swt_acoes.reset_index(level = 0, drop = False)
swt_acoes_month = swt_acoes_month[swt_acoes_month['C/V'] == 'Venda'].resample('M')[['Valor Operação', 'Resultado p/Ação', 'IRRF por Nota']].sum()
swt_acoes_month.columns = ['Valor Operação', 'Resultado Mensal', 'IRRF por Nota']
swt_acoes_month['IRRF Acumulado'] = swt_acoes_month['IRRF por Nota'].cumsum()


#Cálculo do IR: 4 Situações:
#1) Se houver prejuízo, não tem IR e acumula o prejuízo:
#2) Se houver lucro, mas o valor das operações ficar abaixo de 20mil, não tem IR e não abate o prejuízo
#3) Se houver lucro e o valor das operações superar 20mil, abate o prejuízo. Nesse caso:
#3.1) Se, após o abatimento, o valor acumulado ainda for negativo, não tem IR;
#3.2) Se, após o abatimento, o valor acumulado for positivo, tem IR sobre esse saldo. O prejuízo acumulado zera. 

prej = []
ir = []
start_n = 0

for index, row in swt_acoes_month.iterrows():
	if (row['Resultado Mensal'] < 0):
		start_n += row['Resultado Mensal']
		ir.append(0)
	elif (row['Resultado Mensal'] > 0) & (row['Valor Operação'] < 20000):
		start_n += 0 
		ir.append(0)
	else:
		start_n += row['Resultado Mensal']
		if start_n < 0:
			ir.append(0)
		else:
			ir.append(start_n * 0.15)
			start_n = 0
	prej.append(start_n)

swt_acoes_month['Prejuízo a Abater'] = prej
swt_acoes_month['IR'] = ir



#Abatendo IRRF's:
ir_positivo = swt_acoes_month[swt_acoes_month['IR'] > 0]['IRRF Acumulado'].diff()
ir_positivo.name = 'IRRF_diff'

swt_acoes_month = pd.concat([swt_acoes_month, ir_positivo], axis = 1)
swt_acoes_month.fillna(value = {'IRRF_diff': 0}, inplace = True)

irrf_dff = []

for index, row in swt_acoes_month.iterrows():
	if (row['IRRF_diff'] == 0) & (row['IR'] > 0):
		irrf_dff.append(row['IRRF Acumulado'])
	else:
		irrf_dff.append(row['IRRF_diff'])

swt_acoes_month['IRRF_diff'] = irrf_dff

swt_acoes_month['IR Liq'] = swt_acoes_month['IR'] - swt_acoes_month['IRRF Acumulado']
swt_acoes_month['IR Liq'] = swt_acoes_month['IR Liq'].apply(lambda x: x if x > 0 else 0)

swt_acoes_month['Resultado Mensal Líquido'] = swt_acoes_month['Resultado Mensal'] - swt_acoes_month['IR Liq']



#Exporta as DataFrames:
#1) Registros:
swt_acoes.to_csv('registros.csv',
	sep = ';',
	decimal = ',',
	encoding = 'latin-1')


#2) Mensal - agregado:
swt_acoes_month.to_csv('mensal.csv',
	sep = ';',
	decimal = ',',
	encoding = 'latin-1')

