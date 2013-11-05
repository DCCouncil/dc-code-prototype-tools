# Convert a flat sequence of numbered list labels such as
#   1 2 a b 3 4
# into a hierarchical structure like
#   1, 2, [a, b] 3, 4
#
# Works on the sorts of symbols found in the DC Code, which
# get quite interesting like QQ-i (which is between PP and
# either QQ-ii or RR).
#
# Try:
#   1 2 2A 2B A B 3 A B C D E F G H I J K L M N i ii iii iv O P Q R S T U V W X Y Z AA BB BB-i BB-ii CC
# which gives:
#   1 2 2A 2B [A B] 3 [A B C D E F G H I J K L M N [i ii iii iv] O P Q R S T U V W X Y Z AA BB BB-i BB-ii CC

import re

def default_symbol_comparer(a, b):
	# Compares two symbols a and b and returns 0 if b is an appropriate
	# symbol to follow a, or a positive score indicating how bad it is
	# for b to follow a. In the special case when a is None, test whether
	# b is an appropriate initial symbol for a new list.

	if a == None:
		# Check initial symbols.
		if b in ("1", "a", "A", "i", "I"):
			return True
		return False

	# Check for all valid continuations.

	# 1, 2 or 1A, 2
	m = re.match("^(\d+)(\D.*)?$", a)
	if m and re.match("^\d+$", b):
		if int(b) == int(m.group(1)) + 1:
			return True

	# A, B or a, b
	if (re.match("^[A-Z]$", a) and re.match("^[A-Z]$", b)) or (re.match("^[a-z]$", a) and re.match("^[a-z]$", b)):
		if ord(b) == ord(a) + 1:
			return True

	# I, II or i, ii
	roman_numeral_letters = 'MDCLXVI'
	if (re.match("^[%s]+$" % roman_numeral_letters, a) and re.match("^[%s]+$" % roman_numeral_letters, b)) or \
	   (re.match("^[%s]+$" % roman_numeral_letters.lower(), a) and re.match("^[%s]+$" % roman_numeral_letters.lower(), b)):
		if parse_roman_numeral(b) == parse_roman_numeral(a) + 1:
			return True

	# 5, 5A
	m = re.match("^(\d+)(\D.*)$", b)
	if m and m.group(1) == a:
		if default_symbol_comparer(None, m.group(2)):
			return True

	# 5A, 5B
	m = re.match("^(\d+)(\D.*)$", a)
	if m and b.startswith(m.group(1)):
		if default_symbol_comparer(m.group(2), b[len(m.group(1)):]):
			return True

	# Z, AA
	if a == "Z" and b == "AA": return True
	if a == "ZZ" and b == "AAA": return True

	# AA, BB
	def all_same_char(s):
		if len(s) == 0: raise ValueError()
		for i in range(1, len(s)):
			if s[i] != s[0]:
				return False
		return True
	if re.match("^[A-Za-z]{2,}$", a) and re.match("^[A-Za-z]{2,}$", b) and len(a) == len(b) and all_same_char(a) and all_same_char(b):
		if default_symbol_comparer(a[0], b[0]):
			return True

	# ??, ??-i
	b1 = b.split("-", 1)
	if len(b1) == 2 and b1[0] == a:
		if default_symbol_comparer(None, b1[1]):
			return True

	# ??-i, ??-ii
	a1 = a.split("-", 1)
	b1 = b.split("-", 1)
	if len(a1) == 2 and len(b1) == 2 and a1[0] == b1[0]:
		if default_symbol_comparer(a1[1], b1[1]):
			return True

	# AA-i, BB
	a1 = a.split("-", 1)
	if len(a1) == 2:
		if default_symbol_comparer(a1[0], b):
			return True

	return False

def infer_list_indentation(
	symbol_list,
	symbol_comparer=default_symbol_comparer,
	):

	# Work from left-to-right.

	stack = [ [symbol_list[0]] ]

	for s in symbol_list[1:]:
		# Let the user put None's in the list and we'll just put those at
		# their own indent levels.
		if s is None:
			stack.append([s])
			continue

		# Does this continue any symbol on the stack?
		ok_levels = []
		for i in range(len(stack)):
			if stack[i][-1] is not None and symbol_comparer(stack[i][-1], s):
				ok_levels.append(i)

		if len(ok_levels) == 0:
			# Symbol doesn't continue from any symbol on the stack, so this must be an indentation.
			if not symbol_comparer(None, s):
				# It also doesn't appear to be an indentation because it's not an initial
				# symbol.
				#raise ValueError("%s does not continue from any symbol on the stack and is not an initial symbol: %s" % (s, [ss[-1] for ss in stack]) )
				pass
			stack.append([s])
		#elif len(ok_levels) > 1:
		#	raise ValueError("%s continues from multiple symbols on the stack: %s" % (s, [ss[-1] for ss in stack]) )
		else:
			lvl = ok_levels[-1]
			while len(stack) > lvl+1:
				q = stack.pop(-1)
				stack[-1].append(q)
			stack[-1].append(s)
	
	while len(stack) > 1:
		q = stack.pop(-1)
		stack[-1].append(q)

	return stack[0]

# via http://code.activestate.com/recipes/81611-roman-numerals/
roman_numeral_map = tuple(zip(
    (1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1),
    ('M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I')
))
def parse_roman_numeral(n):
    n = n.upper()
    i = result = 0
    for value, symbol in roman_numeral_map:
        while n[i:(i + len(symbol))] == symbol:
            result += value
            i += len(symbol)
    if i != len(n): raise ValueError("Not a roman numeral: %s (parsed up to '%s')" % (n, n[0:i]))
    return result
	
if __name__ == "__main__":
	#ret = infer_list_indentation(['a', '1', '2'])
	#ret = infer_list_indentation(['a', '1', '2', 'A', 'B', 'C', 'D', '3', 'A', 'B', 'C', 'D', 'E', 'F', '4', '5', '6', 'b', '1', 'A', 'B', 'i', 'ii', 'iii', 'iv', '2', 'A', 'B', 'C', 'D', 'E', 'c', '1', '2', 'd', '1', '2', '3', '4', '5', 'A', 'B', '6', '7', 'A', 'B', 'C', 'D', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', 'A', 'B', 'C', 'e', '1', 'A', 'B', 'C', 'D', 'i', 'ii', 'iii', 'iv', 'v', 'I', 'II', 'III', 'E', 'i', 'ii', 'iii', 'iv', 'v', '2', 'f', '1', '2', '3'])
	#ret = infer_list_indentation(['1', '2', '3', '4', '5', '5A', '5B', '5C', 'A', 'B', '6', 'A', 'B', 'C', 'D', 'E', 'F', '7', '8', '8A', '9', '9A', '10', '10A', '11', '12', '13', '13A', '13B', '13C', '14', '14A', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', '15', '15A', '16', '17', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'i', 'ii', 'iii', 'iv', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'BB', 'CC', 'DD', 'EE', 'FF', 'GG', 'HH', 'II', 'JJ', 'KK', 'LL', 'MM', 'NN', 'OO', 'PP', 'QQ', 'QQ-i', 'RR', 'SS', 'TT', 'UU', 'VV', 'WW', 'XX', 'YY', 'ZZ', 'AAA', 'BBB', 'CCC', 'DDD', 'EEE'])
	ret = infer_list_indentation(['1', '2', '3', '4', '5', '5A', '6', '7', '7A', '7B', '8', '9', '10', '11', '11A', '11B', '12', '12A', '12A-i', '12B', '12C', '12D', '13', '14', '14A', '15', '16', '17', '18', '19', '20', 'A', 'i', 'ii', 'iii', 'B', '21', '22', '23', '24', 'A', 'B', 'C', '25', '26', '27', '28', '29', '30', '31'])
	
	def dump(symbols, indent=0):
		for symbol in symbols:
			if isinstance(symbol, list):
				dump(symbol, indent=indent+1)
			else:
				print("  "*indent + symbol)

	dump(ret)