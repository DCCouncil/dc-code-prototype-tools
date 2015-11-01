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
from matchers import Matcher, isint

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

	def next(self, skip=0, skip_empty=True):
		index = self['index'] - self._paras[0]['index']
		try:
			para = Para(self._paras, self._paras[index + 1])
		except:
			return None
		if skip_empty and not para['text']:
			para = para.next(skip_empty=skip_empty)
		if skip:
			return para.next(skip-1, skip_empty)
		else:
			return para

	def last(self):
		return Para(self._paras, self._paras[-1])

	def prev(self, skip=0, skip_empty=True):
		index = self['index'] - self._paras[0]['index']
		if index < 1:
			return None
		para = Para(self._paras, self._paras[index - 1])
		if skip_empty and not para['text']:
			para = para.prev(skip_empty=skip_empty)
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
	
def parse_file(path_to_file):
	doc = open_docx(path_to_file)
	paras = []
	for section in doc['sections']:
		for index, para in enumerate(section['paragraphs'], len(paras)):
			para['index'] = index
		paras += section['paragraphs']

	return paras

def pipeline(*parsers, final_parser=None):
	def _next_parser(dom, para, next_parser=None):
		if parsers:
			return parsers[0](dom, para, pipeline(*parsers[1:], final_parser=final_parser or next_parser))
		elif next_parser:
			return next_parser(dom, para)
		elif final_parser:
			return final_parser(dom, para)
	return _next_parser

def _get_short_title_para(para):
	return  para.search(lambda para: para['text'].startswith('BE IT ENACTED BY THE COUNCIL'))

short_title_re = re.compile(r'(\u201c|")(?P<short_title>.*?)(\u201d|")')
def header(dom, para, next_parser):
	make_node(dom, 'act-header', para['text'])
	para = para.next(skip=3)
	make_node(dom, 'long-title', para['text'])
	make_node(dom, 'short-title', short_title_re.search(_get_short_title_para(para)['text']).group('short_title'))
	body = make_node(dom, 'body')
	para = next_parser(body, para.next())
	return para

def toc(dom, para, next_parser):
	toc_dom = []
	next_para = para.next()
	style = next_para.get('properties', {}).get('style', '')
	while style.startswith('TOC'):
		if not toc_dom:
			toc_dom = [make_node(dom, 'toc')]
		level = int(style[3:])
		runs = next_para['runs']
		toc_dom = toc_dom[:level] + [make_node(toc_dom[level-1], 'toc', container=runs[0]['text'].strip(), page=runs[1]['text'].strip())]
		next_para = para.next()
		style = next_para.get('properties', {}).get('style', '')
		para = next_para

	next_parser(dom, para)
	
def short_title(dom, para, next_parser):
	para = _get_short_title_para(para)
	make_node(dom, 'text', text=para['text'])
	next_parser(dom, para.next())

is_title = Matcher({
	'properties': {'outlineLvl': '0'},
	'text': re.compile(r'^title (?P<num>[\w-]+\.) (?P<heading>.+)', re.I),
}, {
	'properties': {'style': 'Heading1'},
	'text': re.compile(r'^title (?P<num>[\w-]+\.) (?P<heading>.+)', re.I),
})

def title(dom, para, next_parser):
	if is_title(para):
		title_paras = para.split(is_title)
		for title_para in title_paras:
			is_title(title_para)
			title_dom = make_container(dom, prefix='Title', **title_para['text_re'].groupdict())
			next_parser(title_dom, title_para.next())
	else:
		next_parser(dom, para)

is_subtitle = Matcher({
	'properties': {'outlineLvl': '1'},
	'text': re.compile(r'^subtitle (?P<num>[\w-]+\.) (?P<heading>.+)', re.I),
}, {
	'properties': {'style': 'Heading1'},
	'text': re.compile(r'^subtitle (?P<num>[\w-]+\.) (?P<heading>.+)', re.I),
})

def subtitle(dom, para, next_parser):
	if is_subtitle(para):
		subtitle_paras = para.split(is_subtitle)
		for subtitle_para in subtitle_paras:
			is_subtitle(subtitle_para)
			subtitle_dom = make_container(dom, prefix='Subtitle', **subtitle_para['text_re'].groupdict())
			next_parser(subtitle_dom, subtitle_para.next())
	else:
		next_parser(dom, para)

is_section = Matcher({'text': re.compile(r'Sec(,|\.) ?(?P<num>[\w-]+)\.? (?P<heading>[^\(][^.]+\.(\s|$))?(?P<remainder>.*)')})

def _section(dom, para, next_parser):
	section_paras = para.split(is_section)
	for section_para in section_paras:
		if not is_section(section_para):
			make_node(dom, 'error', section_para['text'])
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

para_re = re.compile(r'^(?P<num>\([\w-]+\)) ?(?P<remainder>.*)')
def is_para(indent=None):
	if indent is not None:
		matcher = Matcher({
			'properties': {'indentation': indent},
			'text': para_re,
		}, {
			'runs':[{'text': re.compile(r'^ {{{}}}[^ ]'.format(indent))}],
			'text': para_re,
		})
	else:
		matcher = Matcher({'text': para_re})
	return matcher

is_any_para = is_para()

def _para(dom, para, next_parser):
	if not is_any_para(para):
		make_node(dom, 'error', para['text'])
		return
	run = para['runs'][0]['text']
	indent = para['properties'].get('indentation', len(run) - len(run.lstrip(' ')))
	_is_para = is_para(indent)
	para_paras = para.split(_is_para)

	for para_para in para_paras:
		if not _is_para(para):
			make_node(dom, 'error', para['text'])
			return
		re_sults = para_para['text_re'].groupdict()
		para_dom = make_para(dom, **re_sults)

		if re_sults['remainder']:
			para_para['text'] = re_sults['remainder']
			next_para = para_para
		else:
			next_para = para_para.next()
		if next_para:
			next_parser(para_dom, next_para)

def is_include(para):
	text = para['text'].replace('\u201c', '"').replace('\u201d', '"')
	return bool((text.startswith('"') and (text.count('"') % 2 or text.endswith('".'))))

def is_include_end(para):
	text = para['text'].replace('\u201c', '"').replace('\u201d', '"')
	return bool((text.endswith('".') and (text.startswith('"') or text.count('"') % 2)))

trailing_quote_re = re.compile(r'["\u201d]\.\s*$')
def include(dom, para, next_parser):
	if is_include(para):
		last_include = para.search(is_include_end)
		if last_include is None:
			make_node(dom, 'error', para['text'])
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
			char = '"' if i_para['text'].startswith('"') else '\u201c'
			first_run = i_para['runs'][0]
			first_run['text'] = first_run['text'].replace(char, '', 1)
		last_run = include_para.last().search(lambda para: para['text'], reverse=True)['runs'][-1]
		last_run['text'] = trailing_quote_re.sub('', last_run['text'])

		if len(include_para._paras) > 1 and is_section(include_para):
			section(include_dom, include_para)
		elif is_any_para(include_para):
			paras(include_dom, include_para)
		else:
			for i_para in include_para.paras:
				make_text(dom, i_para['text'])
	if next_para:
		next_parser(dom, next_para)

is_text = lambda para: not (is_any_para(para) or is_include(para) or is_include_end(para))

def text(dom, para, next_parser):
	text_para, next_para = para.leading(matcher=is_text)

	if text_para:
		for text_para in text_para.paras:
			make_text(dom, text_para['text'])

	if not next_para:
		return

	next_para, posttext_para = next_para.trailing(matcher=is_text)

	if next_para:
		next_parser(dom, next_para)

	if posttext_para:
		for text_para in posttext_para.paras:
			make_text(dom, text_para['text'], post=True)

def unhandled(dom, para, next_parser):
	raise(Exception('unhandled paras:', para._paras[para.raw_index:]))

para = pipeline(_para, text, include)
paras = pipeline(
	para,
	para,
	para,
	para,
	para,
	para,
	unhandled,
)
section = pipeline(
	_section,
	text,
	include,
	paras,
)

parser = pipeline(
	header,
	toc,
	short_title,
	title,
	subtitle,
	section,
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
		make_node(section, 'heading', heading, ambig=True)
	return section

def make_para(parent, num, **kwargs):
	para = make_node(parent, 'para', None)
	make_node(para, 'num', num)
	return para

def make_text(parent, text=None, post=None, **kwargs):
	tag = 'postText' if post else 'text'
	if text:
		return make_node(parent, tag, text, ambig=post)
	else:
		return None

def main():
	dom = etree.Element("measure")
	paras = parse_file(sys.argv[1])
	# save copy of doc for debugging
	with open('doc.json', 'w') as f:
		json.dump(paras, f, indent=2)
	slice_index = Para(paras, paras[-1]).search(lambda para: para['text'].startswith('Chairman'), reverse=True).prev()['index']
	paras = paras[0:slice_index]

	parser(dom, Para(paras, paras[0]))

	sys.stdout.buffer.write(etree.tostring(dom, pretty_print=True, encoding="utf-8"))

if __name__ == '__main__':
	main()
