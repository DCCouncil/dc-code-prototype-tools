from enum import Enum
import re

class exists(object):
	def __init__(self, typ=None):
		self.typ = typ

	def __eq__(self, other):
		if self.typ:
			return bool(other) and isinstance(other, self.typ)
		else:
			return bool(other)

class exact(object):
	def __init__(self, pattern):
		self.pattern = pattern

class deepexact(object):
	def __init__(self, pattern):
		self.pattern = pattern

	def __eq__(self, other):
		return self.pattern == other

class optional(object):
	def __init__(self, pattern):
		self.pattern = pattern

	def __eq__(self, other):
		return self.pattern == other

def Matcher(*patterns):
	def _matcher(obj):
		for pattern in patterns:
			if match(pattern, obj):
				return True
		return False
	return _matcher

def TocMatcher(regex):
	return Matcher({
		'properties': {'align': 'center'},
		'text': re.compile(regex),
	})

division =    TocMatcher(r'^Division (?P<num>[\w-]+)\. (?P<heading>.+)')
title =       TocMatcher(r'^Title (?P<num>[\w-]+)\. (?P<heading>.+)')
unit =        TocMatcher(r'^Unit (?P<num>[\w-]+)\. (?P<heading>.+)')
subtitle =    TocMatcher(r'^Subtitle (?P<num>[\w-]+)\. (?P<heading>.+)')
subdivision = TocMatcher(r'^Subdivision (?P<num>[\w-]+)\. (?P<heading>.+)')
article =     TocMatcher(r'^Article (?P<num>[\w-]+)\. (?P<heading>.+)')
chapter =     TocMatcher(r'^Chapter (?P<num>[\w-]+)\. (?P<heading>.+)')
subchapter =  TocMatcher(r'^Subchapter (?P<num>[\w-]+)\. (?P<heading>.+)')
part =        TocMatcher(r'^Part (?P<num>[\w-]+)\. (?P<heading>.+)')
subpart =     TocMatcher(r'^Subpart (?P<num>[\w-]+)\.? (?P<heading>.+)')


history = Matcher({
	'runs': exact([{
		'text': re.compile(r'^\(.*\)$'),
	}]),
	'properties': exact({})
})

placeholder = Matcher({
	'properties': {'style': 'Title'},
	'text': [
		# TODO: handle comma-separated multiple sections (title 22+)
		re.compile(r'\u00a7\u00a7 (?P<section_start>[:.\w-]+) to (?P<section_end>[:.\w-]+)\.( (?P<heading>.+) )?\[(?P<reason>[^\[]+)\]\.'),
		re.compile(r'\u00a7\u00a7 (?P<section_start>[:.\w-]+) to (?P<section_end>[:.\w-]+)\.( (?P<heading>.+))?'),
		re.compile(r'^\u00a7 (?P<section>[:.\w-]+)\.( (?P<heading>.+) )?\[(?P<reason>[^\[]+)\].'),
	]
})

section = Matcher({
	'properties': {'style': 'Title'},
	'text': re.compile(r'^\u00a7 (?P<num>[:.\w-]+)\.( (?P<heading>.+))?'),
})

toc_entry = Matcher({
	'properties': {'indentation': exists()}
})

empty = Matcher({
	'text': ''
})

anytext = Matcher({
	'text': exists(str)
})

centered = Matcher({
	'properties': {'align': 'center'}	
})

section_node = Matcher({
	'runs': [
		{
			'properties': {'b': True},
			'text': [
				re.compile(r'^(?P<spaces> *)(?P<prefix>)(?P<num>\([\w-]+\))\s*$'),
				re.compile(r'^(?P<spaces> *)(?P<prefix>)(?P<num>\w{1,3}(?:-\w{1,3})?\.)\s*$'),
				re.compile(r'^(?P<spaces> *)(?P<prefix>)(?P<num>\([\w-]+\))(?P<num2>\([\w-]+\))\s*$'),
			],
		},
		optional({
			'properties': {'i': True},
			'text': re.compile(r'^(?P<heading>.+?)\s*$'),
		})
	],
})

section_heading = Matcher({
	'properties': {'align': 'center'},
	'text': [
		re.compile(r'^(?P<prefix>)(?P<heading>.+)'),
	],
})

anno = Matcher({
	'properties': {'style': 'Subtitle'},
	'text': re.compile(r'^(?P<heading>[^.]+)')
})


#################################

class NoMatch(BaseException):
	pass

def match_dict(pattern, obj, exact=False, deep_exact=False, optional=False):
	regexes = []
	if not isdict(obj):
		raise NoMatch()

	if (exact or deep_exact) and set(pattern.keys()) != set(obj.keys()):
		raise NoMatch()

	for k, pv in pattern.items():
		try:
			ov = obj[k]
		except KeyError:
			if not isoptional(pv):
				raise NoMatch()
		else:
			if isregex(pv):
				pv = [pv]
			if isregexlist(pv):
				if isstring(ov):
					regexes.append({'obj': obj, 'k': k, 're': pv, 'str': ov, 'optional': optional})
				else:
					raise NoMatch()
			else:
				regexes += match(pv, ov, True, deep_exact=deep_exact)

	return regexes


def match_list(pattern, obj, exact=False, deep_exact=False, optional=False):
	regexes = []
	if not islist(obj):
		raise NoMatch()

	if (exact or deep_exact) and len(pattern) != len(obj):
		raise NoMatch()

	for i, p in enumerate(pattern):
		try:
			o = obj[i]
		except IndexError:
			if not isoptional(p):
				raise NoMatch()
		else:
			regexes += match(p, o, True, deep_exact=deep_exact)
	return regexes


def match(pattern, obj, is_child=False, **kwargs):
	"""
	valid kwargs:
		exact; deep_exact, optional; all default to False
	"""
	regexes = []
	try:
		if pattern == obj:
			pass
		elif isexact(pattern):
			kwargs['exact'] = True
			regexes += match(pattern.pattern, obj, True, **kwargs)
		elif isdeepexact(pattern):
			kwargs['deep_exact'] = True
			regexes += match(pattern.pattern, obj, True, **kwargs)
		elif isoptional(pattern):
			kwargs['optional'] = True
			regexes += match(pattern.pattern, obj, True, **kwargs)
		elif isdict(pattern):
			regexes += match_dict(pattern, obj, **kwargs)
		elif islist(pattern):
			regexes += match_list(pattern, obj, **kwargs)
		else:
			raise NoMatch()
	except NoMatch:
		if not kwargs.get('optional'):
			if is_child:
				raise
			else:
				return False
	if is_child:
		return regexes
	else:
		for regex in regexes:
			key = regex['k'] + '_re'
			for reg in regex['re']:
				match_result = reg.match(regex['str'])
				if match_result:
					regex['obj'][key] = match_result
					break
				elif key in regex['obj']:
					del(regex['obj'][key])
			if key not in regex['obj'] and not regex['optional']:
				return False
		return True

def isdict(obj):
	return isinstance(obj, dict)

def islist(obj):
	return isinstance(obj, list)

_regex = type(re.compile(''))
def isregex(obj):
	return isinstance(obj, _regex)

def isregexlist(obj):
	return islist(obj) and all([isinstance(i, _regex) for i in obj])

def isstring(obj):
	return isinstance(obj, str)

def isint(obj):
	return isinstance(obj, int)

def isexact(obj):
	return isinstance(obj, exact)

def isdeepexact(obj):
	return isinstance(obj, deepexact)

def isoptional(obj):
	return isinstance(obj, optional)
