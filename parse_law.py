#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Convert a DC Council Statute at Large file, for a single statute
# entry, into XML.
#
# python3 make_sal_xml.py A20-003.docx > output/A20-003.xml
# python3 make_sal_xml.py R20-055.docx > output/R20-055.xml
#
# Chome won't normally render an XSLT instruction when loading from a
# file:// URL. To turn off that security restriction, make sure Chrome
# isn't running at all (check if you need to kill it), and then start
# it with this command-line option:
#
# google-chrome --allow-file-access-from-files 

import sys, re, lxml.etree as etree, datetime, json
from worddoc import open_docx
from matchers import Matcher, isint, exists

errors = 0

class Para(dict):
	def __init__(self, paras, para=None):
		self._paras = paras
		if not paras:
			return None
		if para is None:
			para = paras[0]
		if isint(para):
			para = paras[paras[0]['index'] + para]
		super().__init__(para)

	def next(self, skip=0, skip_empty=True, skip_notes=True):
		index = self['index'] - self._paras[0]['index']
		try:
			para = Para(self._paras, self._paras[index + 1])
		except:
			return None
		if skip_empty and not para['text']:
			return para.next(skip, skip_empty)
		if skip_notes and para.get('properties', {}).get('style') == 'MarginNotes':
			return para.next(skip, skip_empty)
		if skip:
			return para.next(skip-1, skip_empty)
		else:
			return para

	def last(self):
		return Para(self._paras, self._paras[-1])

	def prev(self, skip=0, skip_empty=True, skip_notes=True):
		index = self['index'] - self._paras[0]['index']
		if index < 1:
			return None
		para = Para(self._paras, self._paras[index - 1])
		if skip_empty and not para['text']:
			return para.prev(skip, skip_empty)
		if skip_notes and para.get('properties', {}).get('style') == 'MarginNotes':
			return para.prev(skip, skip_empty)
		if skip:
			return para.prev(skip-1, skip_empty)
		else:
			return para

	def leading(self, index=None, matcher=None):
		paras = self._paras[self.raw_index:]
		if not index:
			index = len(paras)
			for i, para in enumerate(paras):
				para = Para(self._paras, para)
				if not matcher(para) and para['text']:
					index = i
					break
		return [Para(paras[:max(index, 0)]), Para(paras[index:])]

	def trailing(self, index=None, matcher=None):
		paras = self._paras[self.raw_index:]
		if not index:
			paras.reverse()
			index = len(paras)
			for i, para in enumerate(paras):
				para = Para(self._paras, para)
				if not matcher(para) and para['text']:
					index = i - 1
					break
			paras.reverse()
		if index <= 0:
			return [self, None]
		return [Para(paras[:-index]), Para(paras[-index:])]

	def search(self, matcher, reverse=False):
		if reverse:
			paras = self._paras[:self.raw_index+1][::-1]
		else:
			paras = self._paras[self.raw_index:]
		for para in paras:
			para = Para(self._paras, para)
			if matcher(para):
				return para

	def split(self, matcher):
		paras = self._paras[self.raw_index:]
		out = []
		working = []
		for para in paras:
			p = Para(self._paras, para)
			if working and matcher(p):
				out.append(working)
				working = []
			working.append(para)
		if working:
			out.append(working)
		return [Para(paras) for paras in out]

	def __getitem__(self, item):
		try:
			return super().__getitem__(item)
		except KeyError:
			if item == 'text':
				return self.text()
			else:
				raise

	def __setitem__(self, key, item):
		self._paras[self.raw_index][key] = item
		super().__setitem__(key, item)

	def text(self, skip=0):
		return "".join(r["text"].strip('\n') for r in self["runs"][skip:]).strip()

	@property
	def raw_index(self):
		return self['index'] - self._paras[0]['index']

	@property
	def paras(self):
	    return [Para(self._paras, para) for para in self._paras]

has_leading_whitespace = Matcher({'runs': [{'text': re.compile(r'^\s*')}]})

def get_indent(para):
	indent = para['properties'].get('indentation', 0) / 720
	if has_leading_whitespace(para):
		indent += para['runs'][0]['text_re'].group().count('\t')
		del(para['runs'][0]['text_re'])
	return int(indent)

def pict_handler(node):
	return "@@PICT@@"

def parse_file(path_to_file):
	doc = open_docx(path_to_file, pict=pict_handler)
	paras = []
	for section in doc['sections']:
		for index, para in enumerate(section['paragraphs'], len(paras)):
			para['index'] = index
			para['indent'] = get_indent(para)
			for runs in para['runs']:
				runs['text'] = runs['text'].replace('\u201c', '"').replace('\u201d', '"')
		paras += section['paragraphs']

	return paras

def pipeline(*parsers, final_parser=None):
	def _next_parser(dom, para, next_parser=None):
		if parsers:
			parser = parsers[0] if callable(parsers[0]) else globals()[parsers[0]]
			return parser(dom, para, pipeline(*parsers[1:], final_parser=final_parser or next_parser))
		elif next_parser:
			return next_parser(dom, para)
		elif final_parser:
			return final_parser(dom, para)
	return _next_parser

def _get_short_title_para(para):
	return  para.search(lambda para: para['text'].startswith('BE IT ENACTED BY THE COUNCIL'))

short_title_re = re.compile(r'(\u201c|")(?P<short_title>.*?)(\u201d|")')
def header(dom, para, next_parser):
	global errors
	bill_num = para.search(lambda para: para['text'].startswith('Bill'))['text'][5:]
	make_node(dom, 'num', bill_num, type='bill')

	para = para.next(skip=1)
	long_title = para['text']
	short_title = short_title_re.search(_get_short_title_para(para)['text']).group('short_title')

	make_node(dom, 'heading', short_title, type='short')
	make_node(dom, 'heading', long_title, type='long')
	make_node(dom, 'meta')
	next_parser(dom, para.next())

	if errors:
		dom.attrib['errors'] = str(errors)
	errors = 0

def toc(dom, para, next_parser):
	toc_dom = []
	next_para = para.next()
	style = next_para.get('properties', {}).get('style', '')
	while style.startswith('TOC'):
		if not toc_dom:
			toc_dom = [make_node(dom, 'toc')]
		if style == 'TOCHeading':
			make_node(toc_dom[0], 'heading', text=next_para.text())
		else:
			level = int(style[3:])
			runs = next_para['runs']
			toc_dom = toc_dom[:level] + [make_node(toc_dom[level-1], 'toc', container=runs[0]['text'].strip(), page=runs[1]['text'].strip())]
		next_para = para.next()
		style = next_para.get('properties', {}).get('style', '')
		para = next_para

	next_parser(dom, para)
	
def short_title(dom, para, next_parser):
	para = _get_short_title_para(para)
	make_text(dom, para)
	next_parser(dom, para.next())

def is_container(prefix):
	return Matcher({
			'text': re.compile(r'^(?P<prefix>{}) (?P<num>[\w-]+\.) (?P<heading>.+)'.format(prefix), re.I),
		})

is_any_container = Matcher({
	'text': re.compile(r'^(?P<prefix>(division|title|subtitle|article|subdivision|chapter|subchapter|part|subpart)) (?P<num>[\w-]+\.) (?P<heading>.+)', re.I),
})

def _container(dom, para, next_parser):
	if is_any_container(para):
		_is_container = is_container(para['text_re'].group('prefix'))
		container_paras = para.split(_is_container)
		for container_para in container_paras:
			_is_container(container_para)
			container_dom = make_container(dom, **container_para['text_re'].groupdict())
			next_para = container_para.next()
			if is_any_container(next_para):
				_container(container_dom, next_para, next_parser)
			else:
				next_parser(container_dom, next_para)
	else:
		next_parser(dom, para)

detect_section = Matcher({'text': re.compile(r'^Sec[,. ;/):-]')})
is_section = Matcher({'text': re.compile(r'^(\u00a7|Sec\.) (?P<num>[\w.-]+)\. (?P<heading>[^\(][^.]+\.(\s[A-Z]|$))?(?P<remainder>.*)')})

def _section(dom, para, next_parser):
	section_paras = para.split(detect_section)
	for section_para in section_paras:
		if not is_section(section_para):
			make_error(dom, section_para, reason='invalid section')
			return
		re_sults = section_para['text_re'].groupdict()
		section_dom = make_section(dom, **re_sults)
		if re_sults['remainder']:
			section_para['text'] = re_sults['remainder']
			next_para = section_para
		else:
			next_para = section_para.next()
		if next_para:
			next_parser(section_dom, next_para)

is_any_para = Matcher({'text': re.compile(r'^(?P<num>\([\w-]+\)) ?(?P<remainder>.*)')})

def is_para(para):
	indent = para['indent']
	def _is_para(para):
		return (para['indent'] == indent) and is_any_para(para)
	return _is_para


def _para(dom, para, next_parser):
	if not is_any_para(para):
		make_error(dom, para, reason='invalid numbered para')
		return
	indent = para['properties'].get('indentation')
	_is_para = is_para(para)
	para_paras = para.split(_is_para)

	for para_para in para_paras:
		# if para_para['index'] >= 25:
		# 	import ipdb
		# 	ipdb.set_trace()
		if not _is_para(para_para):
			make_error(dom, para_para, reason='invalid numbered para')
			continue
		re_sults = para_para['text_re'].groupdict()
		para_dom = make_para(dom, **re_sults)

		if re_sults['remainder']:
			para_para['text'] = re_sults['remainder']
			para_para['indent'] += 1
			next_para = para_para
		else:
			next_para = para_para.next()
		if next_para:
			if is_any_para(next_para):
				para_parser(para_dom, next_para, next_parser)
			else:
				next_parser(para_dom, next_para)

trailing_quote_re = re.compile(r'"(.?)$')

def is_include(para):
	text = para['text']
	return bool((text.startswith('"') and (text.count('"') % 2 or trailing_quote_re.search(text))))

def is_include_end(para):
	text = para['text']
	return bool((trailing_quote_re.search(text) and (text.startswith('"') or text.count('"') % 2)))

def include(dom, para, next_parser):
	# if para['index'] >= 29:
	# 	import ipdb
	# 	ipdb.set_trace()
	if is_include(para):
		last_include = para.search(is_include_end)
		if last_include is None:
			make_error(dom, para)
			return
		else:
			next_para = last_include.next()
			if next_para:
				next_index = next_para.raw_index
				include_para = Para(para._paras[:next_index])
				next_para = Para(para._paras[next_index:])
			else:
				include_para = para
				next_para = None
	else:
		include_para = None
		next_para = para

	if include_para:
		include_dom = make_node(dom, 'include')
		for i_para in include_para.paras:
			if not i_para['text']:
				continue

			text = i_para['text'].replace('\u201c', '"').replace('\u201d', '"')
			if text.startswith('"'):
				i_para['text'] = text[1:]
			elif not text == '@@TABLE@@':
				make_error(include_dom, i_para, 'missing double quote')
		include_para = include_para.paras[0]

		trailing_char = trailing_quote_re.search(last_include['text']).group(1)
		last_include = include_para.last().search(lambda para: para['text'], reverse=True)
		last_include['text'] = trailing_quote_re.sub('', last_include['text'])

		if include_para.get('toc'):
			for i_para in include_para.paras:
				make_text(include_dom, i_para, proof=False)
		if is_any_container(include_para):
			container(include_dom, include_para)
		elif is_section(include_para):
			section(include_dom, include_para)
		elif is_any_para(include_para):
			para_parser(include_dom, include_para)
		else:
			for i_para in include_para.paras:
				make_text(include_dom, i_para)

		if trailing_char:
			make_text(dom, {'text': trailing_char}, proof=False, after=True)

	if next_para:
		next_parser(dom, next_para)

is_text = lambda para: not (is_any_para(para) or is_include(para) or is_include_end(para))

def text(dom, para, next_parser):
	text_para, next_para = para.leading(matcher=is_text)

	if text_para:
		for text_para in text_para.paras:
			make_text(dom, text_para)
		if next_para and 'designation' in text_para.last()['text']: 
			next_para['toc'] = True # hint to include parser whether include is a toc entry

	if not next_para:
		return

	next_para, aftertext_para = next_para.trailing(matcher=is_text)

	if next_para:
		next_parser(dom, next_para)

	if aftertext_para:
		for text_para in aftertext_para.paras:
			make_text(dom, text_para, after=True)

def unhandled(dom, para, next_parser):
	for para in para.paras:
		make_error(dom, para, reason='too confused')

para_parser = pipeline(_para, text, include, 'para_parser')

section = pipeline(
	_section,
	text,
	include,
	para_parser,
)

container = pipeline(
	_container,
	section,
)
parser = pipeline(
	header,
	toc,
	short_title,
	container,
	unhandled,
)

def make_node(parent, tag, text='', **attrs):
	"""Make a node in an XML document."""
	n = etree.Element(tag)
	parent.append(n)
	if text:
		n.text = text
	for k, v in attrs.items():
		if v is None: continue
		if isinstance(v, datetime.datetime):
			v = format_datetime(v)
		elif isinstance(v, (bool, int)):
			v = str(v)
		n.set(k.replace("___", ""), v)
	return n

def make_container(parent, prefix, num, heading):
	prefix = prefix.capitalize()
	container = make_node(parent, 'container', None)
	make_node(container, 'num', num)
	if heading:
		make_node(container, 'heading', heading)
	if prefix:
		if parent.attrib.get('childPrefix', prefix) != prefix:
			raise Exception('all prefixes must be the same but got {} and {}'.format(parent.attrib['childPrefix'], prefix))
		parent.attrib['childPrefix'] = prefix
	return container

def make_section(parent, num, heading=None, **kwargs):
	section = make_node(parent, 'section', None)
	make_node(section, 'num', num)
	if heading:
		make_node(section, 'heading', heading, proof=True)
	return section

def make_para(parent, num, **kwargs):
	para = make_node(parent, 'para', None)
	make_node(para, 'num', num)
	return para

is_auto_numbered = Matcher({'properties': {'num': exists()}})

def make_text(parent, para, after=None, proof=None, **kwargs):
	text = para['text']
	if not text:
		return None
	if '\t' in text or '   ' in text:
		return make_error(parent, para, 'whitespace')
	if is_auto_numbered(para):
		return make_error(parent, para, 'autonumbered')
	text = text.strip()
	tag = 'aftertext' if after else 'text'
	if proof is None:
		proof = (text and not (text[0].isupper() or text[0] in '"\u201c')) 
	return make_node(parent, tag, text, proof=proof or after)

def make_error(dom, para, reason=None):
	global errors
	errors += 1
	error_dom = make_node(dom, 'error', para['text'], reason=reason)

def parse(path, save=False):
	dom = etree.Element("document",
		# attrib={
		# 	"{http://www.w3.org/2001/XMLSchema-instance}schemaLocation": "http://code.dccouncil.us/schemas/law http://dccode.council.local/schemas/law.xsd",
		# },
		# nsmap={
		# 	None: "http://code.dccouncil.us/schemas/law",
		# 	"xsi": "http://www.w3.org/2001/XMLSchema-instance",
  # 	}
  	)
	paras = parse_file(path)
	# save copy of doc for debugging
	if save:
		with open('doc.json', 'w') as f:
			json.dump(paras, f, indent=2)
	parser(dom, Para(paras, paras[0]))

	return dom

if __name__ == '__main__':
	dom = parse(sys.argv[1], True)
	sys.stdout.buffer.write(etree.tostring(dom, pretty_print=True, encoding="utf-8",  xml_declaration=True))
