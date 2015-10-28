#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
this file removes all non-substantive diffs
(spaces, periods, capitalization)
and commits the substantive changes one commit
per title.

useful for reviewing parser output diffs to minimize
regressions.
"""

msg = 'fix levels for inlined docs'

from git import Repo, Blob
import os.path
from collections import OrderedDict
repo = Repo('.')
index = repo.index
diffs = repo.index.diff(None)
total = 0
included = 0

import difflib
import re
leading_whitespace = re.compile('^\s*')
diffs_out = {}

ignore_chars = re.compile(r'[ \s—.-]+', re.UNICODE)

def normalized_equal(a, b):
	a_normalized = ignore_chars.sub('', a).lower()
	b_normalized = ignore_chars.sub('', b).lower()
	return a_normalized == b_normalized

def substantive_diff(a, b):
	a = a.splitlines()
	b = b.splitlines()

	rem = []
	for l in difflib.ndiff(a, b):
		if l[0] == ' ':
			rem = []
		elif l[0] == '-':
			rem.append(l[2:])
		elif l[0] == '+':
			normalized = leading_whitespace.match(l[2:]).group() + ignore_chars.sub('', l[2:]).lower()
			i = None
			for r in rem:
				a_normalized = leading_whitespace.match(r).group() + ignore_chars.sub('', r).lower()
				if normalized == a_normalized or (a_normalized.strip().startswith('<heading>temporary') and normalized.strip().startswith('<heading>temporary')):
					i = b.index(l[2:])
					b.remove(l[2:])
					b.insert(i, r)
					break
			if i is not None: # if a rem was patched to the ins
				rem.remove(r)
			else:
				rem = []
		elif  l[0] == '?':
			continue
		else:
			print(l[0])

	return '\n'.join(b) + '\n'


import io
import gitdb

def make_blob(string, path):
	b = string.encode('utf-8')
	stream = io.BytesIO(b)
	istream = gitdb.IStream('blob', len(b), stream)
	repo.odb.store(istream)
	blob = Blob (repo, istream.binsha, mode=100644, path=path)
	return blob


titles_to_commit = OrderedDict([['index.xml', []], ['Title-1', []], ['Title-2', []], ['Title-3', []], ['Title-4', []], ['Title-5', []], ['Title-6', []], ['Title-7', []], ['Title-8', []], ['Title-9', []], ['Title-10', []], ['Title-11', []], ['Title-12', []], ['Title-13', []], ['Title-14', []], ['Title-15', []], ['Title-16', []], ['Title-17', []], ['Title-18', []], ['Title-19', []], ['Title-20', []], ['Title-21', []], ['Title-22', []], ['Title-23', []], ['Title-24', []], ['Title-25', []], ['Title-26', []], ['Title-27', []], ['Title-28', []], ['Title-29', []], ['Title-29A', []], ['Title-30', []], ['Title-31', []], ['Title-32', []], ['Title-33', []], ['Title-34', []], ['Title-35', []], ['Title-36', []], ['Title-37', []], ['Title-38', []], ['Title-39', []], ['Title-40', []], ['Title-41', []], ['Title-42', []], ['Title-43', []], ['Title-44', []], ['Title-45', []], ['Title-46', []], ['Title-47', []], ['Title-48', []], ['Title-49', []], ['Title-50', []], ['Title-51', []]])

for d in diffs:
	total +=1
	a = d.a_blob.data_stream.read().decode("utf-8", "strict")
	b = open(d.b_path).read()
	if not normalized_equal(a,b):
		diffs_out[d.b_path] = {'a': a, 'b': b}
		new_b = substantive_diff(a, b)
		if normalized_equal(a, new_b):
			continue
		blob = make_blob(new_b, d.b_path)
		title = d.b_path.split('/', 1)[0]
		titles_to_commit[title].append(blob)
		included += 1


for path in repo.untracked_files:
	title = path.split('/', 1)[0]
	titles_to_commit[title].append(path)

for title, paths in titles_to_commit.items():
	if paths:
		print(title, len(paths))
		index.add(paths)
		if msg:
			index.commit('{} - {}'.format(title, msg))
		else:
			index.commit(title)
	else:
		print('skipping', title)
import json
json.dump(diffs_out, open('tmp.json', 'w'), indent=2, sort_keys=True)
print(included, '/', total)

