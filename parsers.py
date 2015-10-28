"""
This is a list of parsers for parsing JSON representation
of the Lexis word document. A parser is a function generator
that accepts a dom, and a NextParser
and returns a paragraph parser function. If the parser
successfully parser the paragraph, it should return True,
otherwise False. The parser maintains any state that is
needed at that level. If it cannot handle the paragraph,
it should create a next_parser from the NextParser
and delegate to that parser.
"""

import re
import lxml.etree as etree
import datetime
import matchers


def parse_division(dom, NextParser):
	next_parser = None
	def _parse_division(para):
		nonlocal next_parser
		if next_parser:
			return next_parser(para)
		elif matchers.division(para):
			div_node = _make_level(dom, 'toc', 'Division', **match.groupdict())
			next_parser = NextParser(div_node)
			return True
		else:
			return True
	return _parse_division

# we don't want repealed info in anything other than sections.
repealed_re=re.compile(r'\. \[.*\]$')


def ParseToc(matcher, prefix, tag='toc'):
	"""
	Creates a parser to parse a TOC node.
	If a TOC node is found in the para,
	a TOC node is created in appended to the dom.
	If a TOC node is not found, it delegates 
	to the next parser. This ensures that, e.g. even
	if the title doesn't contain subchapters, the 
	parts will be caught.
	"""
	def parse_toc(dom, NextParser):
		next_parser = NextParser(dom)
		just_started = False
		def _parse_toc(para):
			nonlocal next_parser, just_started
			if para.get(prefix.lower(), True) and matcher(para):
				match = para['text_re']
				node_data = match.groupdict()
				if node_data['heading']:
					node_data['heading'] = repealed_re.sub('', node_data['heading'])
				toc_node = _make_level(dom, tag, prefix, para=para['index'], **match.groupdict())
				next_parser = NextParser(toc_node)
				just_started = True
				return True
			elif just_started:
				# skip table of contents
				if matchers.toc_entry(para) or matchers.empty(para):
					return True
				else:
					just_started = False
					return next_parser(para)
			else:
				return next_parser(para)
		return _parse_toc
	return parse_toc


def parse_unit(dom, NextParser):
	# must match a unit on the first try,
	# or we will forever delegate to the next parser
	next_parser = NextParser(dom)
	just_started = True
	unit_detected = False
	def _parse_unit(para):
		nonlocal next_parser, just_started, unit_detected

		if (just_started or unit_detected) and matchers.unit(para):
			match = para['text_re']
			node_data = match.groupdict()
			if node_data['heading']:
				node_data['heading'] = repealed_re.sub('', node_data['heading'])
			toc_node = _make_level(dom, 'toc', 'Unit', para=para['index'], **match.groupdict())
			next_parser = NextParser(toc_node)
			unit_detected = True
			just_started = True
			return True
		elif just_started:
			# skip table of contents
			if matchers.toc_entry(para) or matchers.empty(para):
				return True
			else:
				just_started = False
				return next_parser(para)
		elif next_parser:
			return next_parser(para)
		else:
			return False
	return _parse_unit

# units can be found pretty much anywhere, so we check for them wherever they might be found
# parse_unit =       ParseToc(matchers.unit, 'Unit')
parse_division =   ParseToc(matchers.division, 'Division')
parse_title =      ParseToc(matchers.title, 'Title')
parse_subtitle =   ParseToc(matchers.subtitle, 'Subtitle')
parse_article =    ParseToc(matchers.article, 'Article')
parse_subdivision =    ParseToc(matchers.subdivision, 'Subdivision')
parse_chapter =    ParseToc(matchers.chapter, 'Chapter')
parse_subchapter = ParseToc(matchers.subchapter, 'Subchapter')
parse_part =       ParseToc(matchers.part, 'Part')
parse_subpart =    ParseToc(matchers.subpart, 'Subpart')

# parse_section_title = ParseToc(matchers.section_title, 'Title', tag='level')
# parse_section_article = ParseToc(matchers.section_article, 'Article', tag='level')


def parse_section(parse_text_generator, parse_history_generator, parse_anno_generator):
	"""
	parse section text until we detect the history parenthetical,
	then switch to parsing annotations.
	"""
	def _parse_section(dom, NextParser):
		in_text = False
		section_node = None
		anno_node = None
		parse_text = None
		parse_anno = None
		parse_history = None
		ignore = False
		def _parse_section(para):
			nonlocal in_text, section_node, anno_node, parse_text, parse_anno, parse_history, ignore
			if matchers.placeholder(para):
				ignore = para.get('ignore', False)
				if ignore:
					return True
				match = para['text_re']
				section_node = _make_placeholder(dom, para=para['index'], **match.groupdict())
				anno_node = _make_level(None, 'annotations')
				parse_text = parse_text_generator(section_node, NextParser)
				parse_history = parse_history_generator(anno_node, NextParser)
				parse_anno = parse_anno_generator(anno_node, NextParser)
				in_text = True
				return True
			elif matchers.section(para):
				ignore = para.get('ignore', False)
				if ignore:
					return True
				match = para['text_re']
				section_node = _make_level(dom, 'section', None, para=para['index'], **match.groupdict())
				anno_node = _make_level(None, 'annotations')
				parse_text = parse_text_generator(section_node, NextParser)
				parse_history = parse_history_generator(anno_node, NextParser)
				parse_anno = parse_anno_generator(anno_node, NextParser)
				in_text = True
				return True
			elif ignore:
				return True
			elif section_node is not None and (parse_history(para) or parse_anno(para)):
				in_text = False
				section_node.append(anno_node)
				return True
			elif in_text and parse_text(para):
				return True
			else:
				return False
		return _parse_section
	return _parse_section

def parse_history(dom, NextParser):
	found = False
	def _parse_history(para):
		nonlocal found
		if not found and para.get('history', True) and matchers.history(para):
			_make_level(dom, heading="History", text=para['text'])
			found = True
			return True
		return False
	return _parse_history


def parse_section_text(dom, NextParser):
	started = False
	next_parser = NextParser(dom)
	def _parse_section_text(para):
		nonlocal started
		if matchers.empty(para):
			return True
		elif next_parser(para):
			started = True
			return True
		elif not started:
			_make_text(dom, para['text'])
			return True
		else:
			return False
	return _parse_section_text


def _get_para_node_props(para):
	"""
	return para node props 
	({num, indent, text, heading (if exists), prefix (if exists)})
	if a paragraph node. Return empty props, if not a 
	para node.
	"""
	props = {}

	if matchers.section_node(para):
		num_match = para['runs'][0]['text_re']
		props['num'] = num_match.group('num')
		props['indent'] = len(num_match.group('spaces'))
		props['num2'] = None 
		try: 
			props['num2'] = num_match.group('num2')
			return props
		except:
			pass

		# gotta check if heading is the last node in the run. because lexis.
		if para.get('runs', [{}])[-1].get('properties', {}).get('i'):
			heading_para = para['runs'].pop()
			para['runs'].insert(1, heading_para)
			matchers.section_node(para)

		try:
			heading_match = para['runs'][1]['text_re']
		except(IndexError, KeyError):
			skip = 1
		else:
			skip = 2
			props['heading'] = heading_match.group('heading')
		props['text'] = _para_text_content(para, skip)
	return props


def _get_next_level(para):
	""" return the next para level, or none if there is no next para """
	while True:
		para = para['next']()
		if para is None or matchers.history(para):
			return None
		props = _get_para_node_props(para)
		if props:
			return props['indent']


parens_re = re.compile(r'(?P<num>\([\w-]+\))')

def parse_section_nodes(dom, NextParser):
	"""
	recursively parse a section with multiple, numbered 
	(possibly nested) paragraphs
	"""
	next_parser = None
	level = None
	in_child = False
	para_node = None
	def _parse_section_nodes(para):
		nonlocal next_parser, level, in_child, para_node
		props = _get_para_node_props(para)
		if props:
			if level is None:
				level = props['indent']
			if not matchers.isint(level) or props['indent'] > level:
				success = next_parser(para)
				in_child = in_child or success
				return success
			elif props['indent'] < level:
				# if not handled by a parent parser,
				# but still less than our indent level, then
				# don't know how to handle
				raise Exception('unknown indent for', para['index'], para)
			elif props['indent'] == level:
				para_node = _make_level(dom, **props)
				next_parser = parse_section_nodes(para_node, NextParser)
				if props['num2']:
					in_child = True
					_merge(para, {'runs': [{'text': lambda t: parens_re.sub('  ', t, 1)}]})
					para['text'] = _para_text_content(para)
					return next_parser(para)

				in_child = False
				return True

		elif matchers.section_heading(para):
			match = para['text_re']
			if level is None:
				level = match.group('prefix')

			if level == match.group('prefix'):
				heading_node = _make_level(dom, **match.groupdict())
				next_parser = parse_section_nodes(heading_node, NextParser)
				in_child = True
				return True
			else:
				success = next_parser(para)
				in_child = in_child or success
				return success
		elif not matchers.empty(para):
			if in_child and next_parser(para):
				return True
			elif not matchers.centered(para):
				# lookahead to determine if text belongs to node or its parent
				next_level = _get_next_level(para)
				if para_node is not None and next_level and (not matchers.isint(level) or next_level >= level):
					_make_text(para_node, para['text'], para=para['index'])
				else:
					_make_text(dom, para['text'], para=para['index'])
				return True
			else:
				return False
		else:
			return False
	return _parse_section_nodes


def parse_anno(dom, NextParser):
	anno_node = None
	def _parse_anno(para):
		nonlocal anno_node
		if matchers.anno(para):
			match = para['text_re']
			anno_node = _make_level(dom, **match.groupdict())
			return True
		elif anno_node is not None:
			if matchers.anytext(para):
				_make_text(anno_node, para['text'])
			return True
		else:
			return False
	return _parse_anno


def pipeline(*parsers, i=0):
	next_parser = None
	def _next_parser(dom, NextParser=None):
		nonlocal parsers, next_parser
		if NextParser:
			next_parser = NextParser
		try:
			return parsers[i](dom, pipeline(*parsers, i=i+1))
		except IndexError:
			if next_parser:
				return next_parser(dom)
			else:
				return lambda para: False
	return _next_parser

def _make_node(parent, tag, text, **attrs):
	""" Make a node in an XML document. """
	n = etree.Element(tag)
	if parent is not None:
		parent.append(n)
	n.text = text
	for k, v in attrs.items():
		if v is None: continue
		if isinstance(v, datetime.datetime):
			v = format_datetime(v)
		elif isinstance(v, (bool, int)):
			v = str(v)
		n.set(k.replace("___", ""), v)
	return n


def _make_level(parent, typ=None, prefix=None, num=None, heading=None, text=None, para=None, **kwargs):
	"""
	Make a level xml structure:
	<level type="{typ}"><prefix>{prefix}</prefix><num>{num}</num><heading>{heading}</heading></level
	returning the new level object
	"""
	level = _make_node(parent, 'level', None, type=typ, para=para)
	if prefix:
		_make_node(level, 'prefix', prefix)
	if num:
		_make_node(level, 'num', num)
	if heading:
		_make_node(level, 'heading', heading)
	if text:
		_make_text(level, text)
	return level

def _make_placeholder(parent, reason=None, heading=None, section=None, section_start=None, section_end=None, para=None):
	level = _make_node(parent, 'level', None, type='placeholder', para=para)
	if reason:
		_make_node(level, 'reason', reason)
	if section:
		_make_node(level, 'section', section)
	if section_start:
		_make_node(level, 'section-start', section_start)
		_make_node(level, 'section-end', section_end)
		_make_node(level, 'section-range-type', 'range')
	if heading:
		_make_node(level, 'heading', heading)
	return level

def _make_text(parent, text=None, para=None, **kwargs):
	if text:
		return _make_node(parent, 'text', text, para=para)
	else:
		return None

def _para_text_content(p, skip = 0):
	return "".join(r["text"].strip('\n') for r in p["runs"][skip:]).strip()

def _prepend(prepend_text, run=0):
	def _prepend(para):
		para['runs'][run]['text'] = prepend_text + para['runs'][run]['text']
		para['text'] = _para_text_content(para)
		return False
	return _prepend

def _ignore(para):
	return True

def _move_run(old_index, new_index):
	def _move_run(para):
		para['runs'].insert(new_index, para['runs'].pop(old_index))
		return para
	return _move_run

def _merge(old, new):
	if matchers.isdict(old) and matchers.isdict(new):
		for k, n in new.items():
			o = old.get(k)
			old[k] = _merge(o, n)
	elif matchers.islist(old) and matchers.islist(new):
		out = []
		for i, n in enumerate(new):
			try:
				o = old[i]
			except IndexError:
				o = None
			out.append(_merge(o,n))
		old = out
	elif callable(new):
		old = new(old)
	else:
		old = new
	return old

def _update(new_para):
	def _update(para):
		_merge(para, new_para)
		para['text'] = _para_text_content(para)
	return _update

def bulk_apply(fix_fns, fn, start, end):
	""" apply fn to lines start through end, inclusive """
	for i in range(start, end + 1):
		fix_fns[i] = fn

fix_fns = {
	0: _ignore,

	# 2015-06
	# div 1
	175: _move_run(-1, 1),
	178: _move_run(-1, 1),
	181: _move_run(-1, 1),
	190: _move_run(-1, 1),
	# 1-325.331
	16337: _prepend('\u00a7 '),
	# 1-623.02 TODO: fix
	31392: _update({'ignore': True}),
	37528+1: _update({'properties': {'align': None}}),
	# 2-1223.21
	74384+1: _update({'runs': [{'text': '\u00a7 2-1223.21. Corporation’s review of plans and projects of District agencies. [Repealed].'}]}),
	77380+1: _update({'properties': {'align': 'center'}}),
	85972+1: _ignore,
	86018+1: _update({'properties': {'align': 'center'}}),
	129359+4: _update({'runs': [{'text': '§ 5-1051. Definitions.'}]}),

	# # div 2
	210569 + 0: _ignore,
	210569 + 12693: _update({'runs': [{'text': "\u00a7 16-916.01a. \u2014 Appendices to \u00a7\u200216-916.01."}]}),
	210569 + 21850: _update({'history': False}),
	210569 + 26674: _update({'history': False}),

	# # div 3
	237537 + 0: _ignore,
	237537 + 2421: _update({'history': False}),
	237537 + 2494: _update({'history': False}),
	237537 + 2881: _update({'history': False}),
	237537 + 3172: _update({'history': False}),
	237537 + 7010: _update({'history': False}),

	# div 4
	254883 + 0: _ignore,
	254883 + 12072: _update({'runs': [{'text': '\u00a7\u00a7 22-3801 to 22-3802. Indecent acts with children; sodomy. [Repealed].'}]}),
	254883 + 15136: _update({'runs': [{'text': '\u00a7\u00a7 22-4901 to 22-4902. Seduction; seduction by teacher. [Repealed].'}]}),


	# # div 5
	# # article 4; part 1
	280849 + 0: _ignore,

	280849 + 28207 + 4: _update({'runs': [{'text': 'Part 1. General Provisions and Definitions.'}]}),
	280849 + 28208 + 4: _ignore,
	# article 4A; part 1
	280849 + 29593 + 4: _update({'runs': [{'text': 'Part 1. Subject Matter and Definitions.'}]}),
	280849 + 29594 + 4: _ignore,

	280849 + 32390 + 4: _update({'runs': [{'text': 'Part 1. General.'}]}),
	280849 + 32391 + 4: _ignore,
	280849 + 45738 + 4: _prepend(' '),
	280849 + 46257 + 4: _update({'properties': {"align": "center"}}),
	280849 + 65827 + 4: _prepend('    '),
	280849 + 65829 + 4: _prepend('    '),
	280849 + 65831 + 4: _prepend('    '),
	280849 + 65833 + 4: _prepend('    '),

	# NOTE: moved 356337 to its proper place just after 356317
	280849 + 75502 + 4: _prepend('    '),

	# NOTE: moved 356500-356502 to proper place just after 356460
	280849 + 75665 + 4: _prepend('    '),
	280849 + 75667 + 4: _prepend('    '),

	280849 + 104829 + 6: _update({'runs': [{'text': "\u00a7 31-3171.01. Definitions."}]}),
	280849 + 125196 + 10: _update({'runs': [{'text': '\u00a7\u00a7 31-5901 to 31-5902. Required licenses for agents or brokers; compensation to unlicensed agents prohibited; violations; exemption of fraternal associations from provisions; licenses required for authorized solicitors; assignment of licenses; violations. [Repealed].'}]}),
	280849 + 133605 + 10: _update({ "runs": [{"properties": {"b": True }, "text": "    (1) " }, {"text": "    Repealed."} ]}),
	280849 + 133606 + 10: _update({ "runs": [{"properties": {"b": True }, "text": "    (2) " }, {"text": "    Repealed."} ]}),
	280849 + 151597 + 10: _prepend('  '),
	280849 + 153038 + 10: _update({ "runs": [{'properties': {'b': True}, 'text': '  (a) '}, { "properties": { "font": "Calibri" }, "text": "If a public utility proposes an action, it shall prepare and transmit to the Commission a detailed environmental impact statement within 60 days following the submission of the proposal. The environmental impact statement shall describe in detail the proposed action, the necessity for the proposed action, and a brief discussion of the following factors:" } ]}),

	# div 6
	438147 + 0: _ignore,
	438147 + 11156: _ignore,
	438147 + 25389 + 6: _update({'article': False}),
	438147 + 25405 + 6: _update({'article': False}),
	438147 + 25408 + 6: _update({'article': False}),
	438147 + 25430 + 6: _update({'article': False}),
	438147 + 25445 + 6: _update({'article': False}),
	438147 + 25451 + 6: _update({'article': False}),
	438147 + 25459 + 6: _update({'article': False}),
	438147 + 25473 + 6: _update({'article': False}),
	438147 + 25483 + 6: _update({'article': False}),

	# div 7
	465428: _ignore,
	465428 + 2787: _update({'history': False}),
	465428 + 2803: _update({'history': False}),
	465428 + 2819: _update({'history': False}),
	465428 + 2835: _update({'history': False}),
	465428 + 10200: _update({'history': False}),
	465428 + 30328: _update({"runs": [{"text": "\u00a7\u00a7 42-4071 to 42-4072. [Expired]."}]}),

	# div 8
	495791 + 0: _ignore,
	495791 + 29174: _update({'article': False}),
	495791 + 29185: _update({'article': False}),
	495791 + 29205: _update({'article': False}),
	495791 + 29208: _update({'article': False}),
	495791 + 29211: _update({'article': False}),
	495791 + 29223: _update({'article': False}),
	495791 + 29288: _update({'article': False}),
	495791 + 29300: _update({'article': False}),
	495791 + 29320: _update({'article': False}),
	495791 + 29326: _update({'article': False}),
	495791 + 29337: _update({'article': False}),
	495791 + 92301 + 13: _update({'runs': [{'text': '\u00a7 50-301.01. Findings.'}]}),
	495791 + 92357 + 13: _update({'runs': [{'text': '\u00a7 50-301.02. Purposes.'}]}),
	495791 + 92569 + 13: _update({'runs': [{'text': '\u00a7 50-301.04. District of Columbia Taxicab Commission \u2014 Established.'}]}),

}

	# # 2015-03
	# # 1-161
	# 1255: _ignore,
	# # 1-306.33
	# 9353: _ignore,
	# 9355: _ignore,
	# 9357: _ignore,
	# # 1-623.02 TODO: fix
	# 30479: _update({'ignore': True}),
	# # 1-1163.13 ok
	# 45066: _update({'ignore': True}),
	# # 2-218.76
	# 53159: _update({'properties': {'style': 'Subtitle'}}),
	# # 2-1223.21
	# 72360: _update({'runs': [{'text': '\u00a7 2-1223.21. Corporation’s review of plans and projects of District agencies. [Repealed].'}]}),
	# # 9-1103.02
	# 191273: _prepend('  '),
	# 191276: _prepend('  '),
# }

def fixes(dom, NextParser):
	next_parser = NextParser(dom)
	def _fixes(para):
		fix_fn = fix_fns.get(para['index'])
		if fix_fn:
			success = fix_fn(para)
			if success:
				return True
		return next_parser(para)
	return _fixes

Parser = pipeline(
	fixes,
	parse_division,
	parse_title,
	parse_unit,
	parse_subtitle,
	parse_unit,
	parse_subdivision,
	parse_article,
	parse_chapter,
	parse_unit,
	parse_subchapter,
	parse_unit,
	parse_part,
	parse_unit,
	parse_subpart,
	parse_unit,
	parse_section(
		pipeline(
			parse_section_text,
			parse_section_nodes,
		),
		parse_history,
		parse_anno,
	)
)
	