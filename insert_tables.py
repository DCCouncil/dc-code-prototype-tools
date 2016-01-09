import sys, lxml.etree as etree, re

try:
	xml_path = sys.argv[1]
except IndexError:
	xml_path = '2015-06.xml'

try:
	tables_path = sys.argv[2]
except IndexError:
	tables_path = 'tables.xml'

try:
	out_path = sys.argv[3]
except IndexError:
	out_path = '2015-06t.xml'

with open(xml_path) as f:
	xml = f.read() # etree.parse(f).getroot()

with open(tables_path or 'tables.xml') as f:
	Tables = etree.parse(f).getroot()

num_re = re.compile('<num>(?P<num>.+?)</num>')
table_re = re.compile(r'@@TABLE@@')
sections = xml.split('<section>\n')

out = []
for section in sections:
	try:
		num = num_re.search(section).group(1)
	except:
		import ipdb
		ipdb.set_trace()
	section_tables = Tables.find('section[@id="{}"]'.format(num))
	if section_tables is not None:
		tables = section_tables.getchildren()
		i = 0
		def replacement(match):
			global i
			table = tables[i]
			out = etree.tostring(table, pretty_print=True, encoding='utf-8').decode('utf-8')
			table.set('inserted', 'true')
			i = i + 1
			return out
		out.append(table_re.sub(replacement, section))
	else:
		out.append(section)

if len(Tables.findall('section/table[@inserted]')) != len(Tables.findall('section/table')):
	import ipdb
	ipdb.set_trace()
	raise Exception('some tables not inserted')

out = '<section>\n'.join(out).encode('utf-8')
dom = etree.fromstring(out)

with open(out_path, 'wb') as f:
	f.write(etree.tostring(dom, pretty_print=True, encoding="utf-8"))
