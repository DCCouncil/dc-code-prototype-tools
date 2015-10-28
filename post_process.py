#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
convert to closer to the old version to improve usefullness of diffs
"""
import re, sys

raw_replacements = (
	(r' para="\d+"', ''),
	(r'“', '"'),
	(r'”', '"'),
	(r'’', '\''),
	(r'‘', '\''),
	(r'<heading>Section references</heading>', '<heading>Section References</heading>'),
	(r'<heading>Cross references</heading>', '<heading>Cross References</heading>'),
	(r'<heading>Legislative history', '<heading>Legislative History'),
	(r"<heading>Editor's notes</heading>", '<heading>Editor’s Notes</heading>'),
	(r'<heading>Effect of amendments</heading>', '<heading>Effect of Amendments</heading>'),
	(r'<heading>Emergency legislation</heading>', '<heading>Emergency Legislation</heading>'),
	(r'<heading>References in text</heading>', '<heading>References in Text</heading>'),
	(r'<heading>Effective dates</heading>', '<heading>Effective Dates</heading>'),
	(r'<heading>Short title</heading>', '<heading>Short Title</heading>'),
	(r'<heading>Temporary legislation</heading>', '<heading>Temporary Legislation</heading>'),
	(r'<heading>New implementing regulations</heading>', '<heading>New Implementing Regulations</heading>'),
	(r'  ', ' '),
	(r'\( ', '('),
	# (r'', ''),
)

replacements = [(re.compile(x), y) for x,y in raw_replacements]

def process(in_file_name, out_file_name):
	with open(in_file_name, 'r') as infile:
		with open(out_file_name, 'w') as outfile:
			for line in infile.readlines():
				for replacement in replacements:
					line = re.sub(replacement[0], replacement[1], line)
				outfile.write(line)

if __name__ == '__main__':
	process(sys.argv[1], sys.argv[2])
