"""Build ``datasets/benchmark.json`` – the CodeMind AI custom Python bug dataset.

Every example is written by hand below (buggy program, reference fix, intended
behaviour, explanation and test *calls*). The builder then:

1. computes each test's expected value by running the **reference** solution
   (our own trusted code, run in a subprocess with a timeout),
2. checks that the reference passes every test and the buggy version fails at
   least one (or does not parse), so every bug is observable,
3. derives the buggy line numbers with difflib,
4. assigns a deterministic dev/eval split (every 4th example → dev) to avoid
   benchmark leakage when tuning prompts, and
5. splits each example's tests into ``validation_tests`` (visible to the repair
   loop) and ``heldout_tests`` (used only for scoring).

Run:  python -m datasets.build_dataset
"""

from __future__ import annotations

import difflib
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

OUT = Path(__file__).with_name("benchmark.json")
EXAMPLES: list[dict] = []


def ex(category: str, difficulty: str, intended: str, buggy: str, fixed: str, calls: list[str],
       explanation: str, raises: list[tuple[str, str]] | None = None) -> None:
    """Register one example. ``calls`` are expressions whose expected values come from ``fixed``."""
    EXAMPLES.append({"category": category, "difficulty": difficulty, "intended_behavior": intended,
                     "buggy_code": textwrap.dedent(buggy).strip("\n") + "\n",
                     "fixed_code": textwrap.dedent(fixed).strip("\n") + "\n",
                     "calls": calls, "raises": raises or [], "explanation": explanation})


# =============================================================================
# 1. Syntax errors
# =============================================================================
ex("syntax_error", "easy", "Return True if n is even.",
   """
   def is_even(n)
       return n % 2 == 0
   """, """
   def is_even(n):
       return n % 2 == 0
   """, ["is_even(4)", "is_even(7)", "is_even(0)", "is_even(-2)"], "Missing colon after the function signature.")
ex("syntax_error", "easy", "Return the square of x.",
   """
   def square(x):
       return (x * x
   """, """
   def square(x):
       return (x * x)
   """, ["square(3)", "square(-4)", "square(0)", "square(1.5)"], "Unclosed parenthesis.")
ex("syntax_error", "easy", "Return a greeting for the given name.",
   """
   def greet(name):
       return "Hello, " + name + "!
   """, """
   def greet(name):
       return "Hello, " + name + "!"
   """, ["greet('Ana')", "greet('')", "greet('Bo')"], "Unterminated string literal.")
ex("syntax_error", "easy", "Return 'positive', 'negative' or 'zero'.",
   """
   def sign(n):
       if n > 0:
           return "positive"
       elif n < 0
           return "negative"
       return "zero"
   """, """
   def sign(n):
       if n > 0:
           return "positive"
       elif n < 0:
           return "negative"
       return "zero"
   """, ["sign(5)", "sign(-3)", "sign(0)"], "Missing colon after elif condition.")
ex("syntax_error", "easy", "Return True if x equals 10.",
   """
   def is_ten(x):
       if x = 10:
           return True
       return False
   """, """
   def is_ten(x):
       if x == 10:
           return True
       return False
   """, ["is_ten(10)", "is_ten(3)", "is_ten(-10)"], "Assignment '=' used instead of comparison '=='.")
ex("syntax_error", "medium", "Return a list of squares of 0..n-1.",
   """
   def squares(n):
       return [i * i for i in range(n]
   """, """
   def squares(n):
       return [i * i for i in range(n)]
   """, ["squares(4)", "squares(0)", "squares(1)"], "Mismatched brackets in the comprehension.")
ex("syntax_error", "easy", "Return the largest element of a non-empty list.",
   """
   def largest(xs):
       best = xs[0]
       for x in xs
           if x > best:
               best = x
       return best
   """, """
   def largest(xs):
       best = xs[0]
       for x in xs:
           if x > best:
               best = x
       return best
   """, ["largest([3, 9, 2])", "largest([-5, -1])", "largest([7])"], "Missing colon after the for statement.")
ex("syntax_error", "medium", "Return a dict mapping each word to its length.",
   """
   def lengths(words):
       return {w: len(w) for w in words
   """, """
   def lengths(words):
       return {w: len(w) for w in words}
   """, ["lengths(['a', 'abc'])", "lengths([])"], "Unclosed dictionary comprehension brace.")
ex("syntax_error", "easy", "Return n factorial.",
   """
   def fact(n):
       result = 1
       for i in range(2, n + 1):
           result *= i
       retrun result
   """, """
   def fact(n):
       result = 1
       for i in range(2, n + 1):
           result *= i
       return result
   """, ["fact(5)", "fact(0)", "fact(1)", "fact(10)"], "Misspelled keyword 'return'.")
ex("syntax_error", "medium", "Return the average of two numbers.",
   """
   def avg(a, b):
       return (a + b) / 2)
   """, """
   def avg(a, b):
       return (a + b) / 2
   """, ["avg(2, 4)", "avg(1, 2)", "avg(-3, 3)"], "Extra closing parenthesis.")

# =============================================================================
# 2. Indentation errors
# =============================================================================
ex("indentation_error", "easy", "Return the larger of two numbers.",
   """
   def maximum(a, b):
       if a > b:
       return a
       return b
   """, """
   def maximum(a, b):
       if a > b:
           return a
       return b
   """, ["maximum(3, 9)", "maximum(9, 3)", "maximum(4, 4)"], "Body of the if statement is not indented.")
ex("indentation_error", "easy", "Return the sum of a list.",
   """
   def total(xs):
       s = 0
       for x in xs:
       s += x
       return s
   """, """
   def total(xs):
       s = 0
       for x in xs:
           s += x
       return s
   """, ["total([1, 2, 3])", "total([])", "total([-1, 1])"], "Loop body is not indented.")
ex("indentation_error", "easy", "Return the absolute value of n.",
   """
   def absolute(n):
     if n < 0:
           return -n
       return n
   """, """
   def absolute(n):
       if n < 0:
           return -n
       return n
   """, ["absolute(-5)", "absolute(5)", "absolute(0)"], "Inconsistent dedent does not match any outer level.")
ex("indentation_error", "easy", "Return the string reversed.",
   """
   def reverse(s):
   return s[::-1]
   """, """
   def reverse(s):
       return s[::-1]
   """, ["reverse('abc')", "reverse('')", "reverse('a')"], "Function body is not indented.")
ex("indentation_error", "medium", "Count vowels in a string.",
   """
   def vowels(s):
       count = 0
       for ch in s.lower():
           if ch in "aeiou":
               count += 1
         return count
   """, """
   def vowels(s):
       count = 0
       for ch in s.lower():
           if ch in "aeiou":
               count += 1
       return count
   """, ["vowels('Hello')", "vowels('xyz')", "vowels('AEIOU')"], "Return statement has an invalid indentation level.")
ex("indentation_error", "easy", "Return 'even' or 'odd'.",
   """
   def parity(n):
       if n % 2 == 0:
           return "even"
       else:
       return "odd"
   """, """
   def parity(n):
       if n % 2 == 0:
           return "even"
       else:
           return "odd"
   """, ["parity(2)", "parity(3)", "parity(0)"], "Else body is not indented.")
ex("indentation_error", "medium", "Return the list without negative numbers.",
   """
   def non_negative(xs):
       out = []
       for x in xs:
           if x >= 0:
               out.append(x)
           return out
   """, """
   def non_negative(xs):
       out = []
       for x in xs:
           if x >= 0:
               out.append(x)
       return out
   """, ["non_negative([1, -2, 3])", "non_negative([-1, -2])", "non_negative([0, 5, 6])"],
   "Return is indented inside the loop, so the function returns after the first element.")
ex("indentation_error", "medium", "Return the number of words longer than k characters.",
   """
   def long_words(words, k):
       count = 0
       for w in words:
           if len(w) > k:
               count += 1
               return count
       return count
   """, """
   def long_words(words, k):
       count = 0
       for w in words:
           if len(w) > k:
               count += 1
       return count
   """, ["long_words(['aa', 'bbbb', 'ccccc'], 3)", "long_words([], 1)", "long_words(['x'], 0)"],
   "Return is wrongly nested inside the if block, ending the loop early.")

# =============================================================================
# 3. Undefined variables
# =============================================================================
ex("undefined_variable", "easy", "Return the average of a non-empty list.",
   """
   def average(numbers):
       total = 0
       for n in numbers:
           total += n
       return totl / len(numbers)
   """, """
   def average(numbers):
       total = 0
       for n in numbers:
           total += n
       return total / len(numbers)
   """, ["average([1, 2, 3])", "average([5])", "average([-2, 2])"], "Typo: 'totl' instead of 'total'.")
ex("undefined_variable", "easy", "Return the area of a rectangle.",
   """
   def area(width, height):
       return width * heigth
   """, """
   def area(width, height):
       return width * height
   """, ["area(2, 3)", "area(0, 5)", "area(1.5, 2)"], "Typo: 'heigth' is undefined.")
ex("undefined_variable", "easy", "Return the number of characters in s, excluding spaces.",
   """
   def count_chars(s):
       cleaned = s.replace(" ", "")
       return len(clean)
   """, """
   def count_chars(s):
       cleaned = s.replace(" ", "")
       return len(cleaned)
   """, ["count_chars('a b c')", "count_chars('')", "count_chars('abc')"], "'clean' was never defined.")
ex("undefined_variable", "medium", "Return the maximum value and its index.",
   """
   def max_with_index(xs):
       best_i = 0
       for i in range(1, len(xs)):
           if xs[i] > xs[best_i]:
               best_i = i
       return xs[best_i], best_index
   """, """
   def max_with_index(xs):
       best_i = 0
       for i in range(1, len(xs)):
           if xs[i] > xs[best_i]:
               best_i = i
       return xs[best_i], best_i
   """, ["max_with_index([3, 8, 1])", "max_with_index([5])", "max_with_index([1, 2, 2])"],
   "'best_index' is undefined; the variable is called 'best_i'.")
ex("undefined_variable", "easy", "Convert Celsius to Fahrenheit.",
   """
   def to_fahrenheit(c):
       return c * 9 / 5 + offset
   """, """
   def to_fahrenheit(c):
       offset = 32
       return c * 9 / 5 + offset
   """, ["to_fahrenheit(0)", "to_fahrenheit(100)", "to_fahrenheit(-40)"], "'offset' is used before being defined.")
ex("undefined_variable", "medium", "Return the list of words in upper case.",
   """
   def shout(words):
       return [word.upper() for w in words]
   """, """
   def shout(words):
       return [w.upper() for w in words]
   """, ["shout(['a', 'bc'])", "shout([])"], "Comprehension uses 'word' but the loop variable is 'w'.")
ex("undefined_variable", "medium", "Count occurrences of each character.",
   """
   def char_counts(s):
       counts = {}
       for ch in s:
           counts[ch] = count.get(ch, 0) + 1
       return counts
   """, """
   def char_counts(s):
       counts = {}
       for ch in s:
           counts[ch] = counts.get(ch, 0) + 1
       return counts
   """, ["char_counts('aab')", "char_counts('')", "char_counts('xyz')"], "'count' is a typo for 'counts'.")
ex("undefined_variable", "easy", "Return the full name 'first last'.",
   """
   def full_name(first, last):
       return frist + " " + last
   """, """
   def full_name(first, last):
       return first + " " + last
   """, ["full_name('Ada', 'Lovelace')", "full_name('A', 'B')"], "Typo 'frist'.")
ex("undefined_variable", "medium", "Return the running totals of a list.",
   """
   def running_totals(xs):
       out = []
       for x in xs:
           acc += x
           out.append(acc)
       return out
   """, """
   def running_totals(xs):
       out = []
       acc = 0
       for x in xs:
           acc += x
           out.append(acc)
       return out
   """, ["running_totals([1, 2, 3])", "running_totals([])", "running_totals([5, -5])"],
   "'acc' is never initialised (UnboundLocalError).")
ex("undefined_variable", "medium", "Return the number of even numbers in the list.",
   """
   def count_even(nums):
       for n in nums:
           if n % 2 == 0:
               evens += 1
       return evens
   """, """
   def count_even(nums):
       evens = 0
       for n in nums:
           if n % 2 == 0:
               evens += 1
       return evens
   """, ["count_even([1, 2, 4])", "count_even([])", "count_even([1, 3])"], "Counter 'evens' is never initialised.")

# =============================================================================
# 4. Type-related issues
# =============================================================================
ex("type_issue", "easy", "Return 'NAME is AGE years old'.",
   """
   def describe(name, age):
       return name + " is " + age + " years old"
   """, """
   def describe(name, age):
       return name + " is " + str(age) + " years old"
   """, ["describe('Alice', 30)", "describe('Bob', 0)"], "Cannot concatenate str and int; convert with str().")
ex("type_issue", "easy", "Return the sum of numbers given as strings.",
   """
   def add_strings(a, b):
       return a + b
   """, """
   def add_strings(a, b):
       return int(a) + int(b)
   """, ["add_strings('2', '3')", "add_strings('10', '-4')"], "String concatenation instead of numeric addition.")
ex("type_issue", "medium", "Return the length of each item in a list of strings as a list.",
   """
   def item_lengths(items):
       return len(items)
   """, """
   def item_lengths(items):
       return [len(item) for item in items]
   """, ["item_lengths(['ab', 'c'])", "item_lengths([])"], "Returns the list length instead of item lengths.")
ex("type_issue", "medium", "Return the mean as a float, e.g. mean([1, 2]) == 1.5.",
   """
   def mean(xs):
       return sum(xs) // len(xs)
   """, """
   def mean(xs):
       return sum(xs) / len(xs)
   """, ["mean([1, 2])", "mean([3, 4, 5])", "mean([1])"], "Integer division '//' truncates the result.")
ex("type_issue", "medium", "Return a new list with x appended, without modifying the input list.",
   """
   def with_item(xs, x):
       return xs.append(x)
   """, """
   def with_item(xs, x):
       return xs + [x]
   """, ["with_item([1], 2)", "with_item([], 'a')"], "list.append returns None.")
ex("type_issue", "medium", "Return the words of a sentence sorted alphabetically.",
   """
   def sorted_words(sentence):
       words = sentence.split()
       return words.sort()
   """, """
   def sorted_words(sentence):
       words = sentence.split()
       return sorted(words)
   """, ["sorted_words('b a c')", "sorted_words('')"], "list.sort() sorts in place and returns None.")
ex("type_issue", "easy", "Return the number repeated as a string n times, e.g. repeat(7, 3) == '777'.",
   """
   def repeat(digit, n):
       return digit * n
   """, """
   def repeat(digit, n):
       return str(digit) * n
   """, ["repeat(7, 3)", "repeat(0, 1)", "repeat(5, 0)"], "Multiplying an int multiplies numerically.")
ex("type_issue", "medium", "Parse 'a,b,c' integers and return their sum.",
   """
   def csv_sum(text):
       return sum(text.split(","))
   """, """
   def csv_sum(text):
       return sum(int(part) for part in text.split(","))
   """, ["csv_sum('1,2,3')", "csv_sum('10')", "csv_sum('-1,1')"], "Cannot sum strings; convert to int first.")
ex("type_issue", "medium", "Return the keys of a dict as a sorted list.",
   """
   def sorted_keys(d):
       return d.keys().sort()
   """, """
   def sorted_keys(d):
       return sorted(d.keys())
   """, ["sorted_keys({'b': 1, 'a': 2})", "sorted_keys({})"], "dict_keys has no sort() method.")
ex("type_issue", "hard", "Return the first character of each word as a string.",
   """
   def initials(sentence):
       return "".join(word[0] for word in sentence)
   """, """
   def initials(sentence):
       return "".join(word[0] for word in sentence.split())
   """, ["initials('hello big world')", "initials('a')"], "Iterating a string yields characters, not words.")

# =============================================================================
# 5. Missing imports
# =============================================================================
ex("missing_import", "easy", "Return the hypotenuse of a right triangle.",
   """
   def hypotenuse(a, b):
       return math.sqrt(a ** 2 + b ** 2)
   """, """
   import math


   def hypotenuse(a, b):
       return math.sqrt(a ** 2 + b ** 2)
   """, ["hypotenuse(3, 4)", "hypotenuse(5, 12)", "hypotenuse(0, 0)"], "'math' is used but never imported.")
ex("missing_import", "easy", "Return the circle area for radius r.",
   """
   def circle_area(r):
       return pi * r * r
   """, """
   from math import pi


   def circle_area(r):
       return pi * r * r
   """, ["circle_area(1)", "circle_area(0)", "circle_area(2.5)"], "'pi' is not imported from math.")
ex("missing_import", "medium", "Return the most common item.",
   """
   def most_common(items):
       return Counter(items).most_common(1)[0][0]
   """, """
   from collections import Counter


   def most_common(items):
       return Counter(items).most_common(1)[0][0]
   """, ["most_common([1, 2, 2, 3])", "most_common(['a'])"], "Counter is not imported from collections.")
ex("missing_import", "medium", "Group words by their first letter.",
   """
   def group_by_letter(words):
       groups = defaultdict(list)
       for w in words:
           groups[w[0]].append(w)
       return dict(groups)
   """, """
   from collections import defaultdict


   def group_by_letter(words):
       groups = defaultdict(list)
       for w in words:
           groups[w[0]].append(w)
       return dict(groups)
   """, ["group_by_letter(['apple', 'avocado', 'banana'])", "group_by_letter([])"], "defaultdict is not imported.")
ex("missing_import", "easy", "Return the greatest common divisor of a and b.",
   """
   def gcd(a, b):
       return math.gcd(a, b)
   """, """
   import math


   def gcd(a, b):
       return math.gcd(a, b)
   """, ["gcd(12, 18)", "gcd(7, 5)", "gcd(0, 9)"], "'math' module not imported.")
ex("missing_import", "medium", "Return the product of all numbers.",
   """
   def product(xs):
       return reduce(lambda a, b: a * b, xs, 1)
   """, """
   from functools import reduce


   def product(xs):
       return reduce(lambda a, b: a * b, xs, 1)
   """, ["product([1, 2, 3, 4])", "product([])", "product([5])"], "reduce is in functools in Python 3.")
ex("missing_import", "medium", "Return the k smallest numbers in ascending order.",
   """
   def k_smallest(xs, k):
       return heapq.nsmallest(k, xs)
   """, """
   import heapq


   def k_smallest(xs, k):
       return heapq.nsmallest(k, xs)
   """, ["k_smallest([5, 1, 4, 2], 2)", "k_smallest([], 3)"], "heapq is not imported.")
ex("missing_import", "medium", "Parse a JSON string and return the value of key 'name'.",
   """
   def get_name(text):
       return json.loads(text)["name"]
   """, """
   import json


   def get_name(text):
       return json.loads(text)["name"]
   """, ["get_name('{\"name\": \"Ana\"}')", "get_name('{\"name\": \"Bo\", \"age\": 3}')"], "json is not imported.")

# =============================================================================
# 6. Logical errors (intended behaviour known)
# =============================================================================
ex("logical_error", "easy", "Return the sum of integers from 1 to n inclusive.",
   """
   def sum_to_n(n):
       total = 0
       for i in range(1, n):
           total += i
       return total
   """, """
   def sum_to_n(n):
       total = 0
       for i in range(1, n + 1):
           total += i
       return total
   """, ["sum_to_n(5)", "sum_to_n(1)", "sum_to_n(0)", "sum_to_n(100)"], "Off-by-one: range excludes n.")
ex("logical_error", "easy", "Return the sum of a and b.",
   """
   def add(a, b):
       return a - b
   """, """
   def add(a, b):
       return a + b
   """, ["add(2, 3)", "add(-1, 1)", "add(0, 0)"], "Wrong operator: subtraction instead of addition.")
ex("logical_error", "easy", "Return True if n is a leap year.",
   """
   def is_leap(year):
       return year % 4 == 0 and year % 100 != 0
   """, """
   def is_leap(year):
       return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
   """, ["is_leap(2000)", "is_leap(1900)", "is_leap(2024)", "is_leap(2023)"], "Missing the divisible-by-400 rule.")
ex("logical_error", "medium", "Return the index of target in a sorted list, or -1.",
   """
   def binary_search(arr, target):
       low, high = 0, len(arr) - 1
       while low < high:
           mid = (low + high) // 2
           if arr[mid] == target:
               return mid
           elif arr[mid] < target:
               low = mid + 1
           else:
               high = mid - 1
       return -1
   """, """
   def binary_search(arr, target):
       low, high = 0, len(arr) - 1
       while low <= high:
           mid = (low + high) // 2
           if arr[mid] == target:
               return mid
           elif arr[mid] < target:
               low = mid + 1
           else:
               high = mid - 1
       return -1
   """, ["binary_search([1, 3, 5, 7], 7)", "binary_search([1, 3, 5], 4)", "binary_search([2], 2)",
         "binary_search([], 1)"], "Loop condition must be low <= high to check the last element.")
ex("logical_error", "easy", "Return the maximum of a list of numbers.",
   """
   def find_max(xs):
       best = 0
       for x in xs:
           if x > best:
               best = x
       return best
   """, """
   def find_max(xs):
       best = xs[0]
       for x in xs:
           if x > best:
               best = x
       return best
   """, ["find_max([3, 7, 2])", "find_max([-5, -2, -9])", "find_max([4])"], "Starting at 0 fails for negative lists.")
ex("logical_error", "easy", "Return True if s is a palindrome (case-insensitive).",
   """
   def is_palindrome(s):
       return s == s[::-1]
   """, """
   def is_palindrome(s):
       s = s.lower()
       return s == s[::-1]
   """, ["is_palindrome('Racecar')", "is_palindrome('abc')", "is_palindrome('')"], "Case is not normalised.")
ex("logical_error", "medium", "Return n factorial (n >= 0).",
   """
   def factorial(n):
       if n == 0:
           return 0
       return n * factorial(n - 1)
   """, """
   def factorial(n):
       if n == 0:
           return 1
       return n * factorial(n - 1)
   """, ["factorial(0)", "factorial(5)", "factorial(1)"], "Base case must return 1.")
ex("logical_error", "medium", "Return the n-th Fibonacci number with fib(0)=0 and fib(1)=1.",
   """
   def fib(n):
       a, b = 0, 1
       for _ in range(n):
           a, b = b, a + b
       return b
   """, """
   def fib(n):
       a, b = 0, 1
       for _ in range(n):
           a, b = b, a + b
       return a
   """, ["fib(0)", "fib(1)", "fib(2)", "fib(10)"], "Returns the next Fibonacci number instead of the n-th.")
ex("logical_error", "easy", "Return the number of items strictly greater than the threshold.",
   """
   def count_above(xs, threshold):
       return sum(1 for x in xs if x >= threshold)
   """, """
   def count_above(xs, threshold):
       return sum(1 for x in xs if x > threshold)
   """, ["count_above([1, 5, 5, 9], 5)", "count_above([], 0)", "count_above([1, 2], 0)"],
   "Uses >= although strictly greater is required.")
ex("logical_error", "medium", "Return True if n is prime.",
   """
   def is_prime(n):
       if n < 2:
           return False
       for d in range(2, n // 2):
           if n % d == 0:
               return False
       return True
   """, """
   def is_prime(n):
       if n < 2:
           return False
       for d in range(2, int(n ** 0.5) + 1):
           if n % d == 0:
               return False
       return True
   """, ["is_prime(4)", "is_prime(2)", "is_prime(9)", "is_prime(17)", "is_prime(1)"],
   "Loop bound n // 2 misses divisors for small numbers such as 4.")
ex("logical_error", "easy", "Return the last element of a non-empty list.",
   """
   def last(xs):
       return xs[len(xs)]
   """, """
   def last(xs):
       return xs[-1]
   """, ["last([1, 2, 3])", "last(['a'])"], "Index len(xs) is out of range.")
ex("logical_error", "medium", "Return the second largest distinct value.",
   """
   def second_largest(xs):
       values = sorted(xs)
       return values[-2]
   """, """
   def second_largest(xs):
       values = sorted(set(xs))
       return values[-2]
   """, ["second_largest([1, 3, 3])", "second_largest([5, 1, 4])"], "Duplicates are not removed.")
ex("logical_error", "medium", "Return the list reversed (without modifying the input).",
   """
   def reversed_list(xs):
       out = []
       for i in range(len(xs) - 1, 0, -1):
           out.append(xs[i])
       return out
   """, """
   def reversed_list(xs):
       out = []
       for i in range(len(xs) - 1, -1, -1):
           out.append(xs[i])
       return out
   """, ["reversed_list([1, 2, 3])", "reversed_list([])", "reversed_list(['a'])"], "Range stops before index 0.")
ex("logical_error", "easy", "Return the grade: A for >= 90, B for >= 80, C otherwise.",
   """
   def grade(score):
       if score >= 80:
           return "B"
       elif score >= 90:
           return "A"
       return "C"
   """, """
   def grade(score):
       if score >= 90:
           return "A"
       elif score >= 80:
           return "B"
       return "C"
   """, ["grade(95)", "grade(85)", "grade(50)", "grade(90)"], "Conditions are checked in the wrong order.")
ex("logical_error", "medium", "Return the number of vowels in s (a, e, i, o, u, any case).",
   """
   def count_vowels(s):
       return sum(1 for ch in s if ch in "aeiou")
   """, """
   def count_vowels(s):
       return sum(1 for ch in s.lower() if ch in "aeiou")
   """, ["count_vowels('HELLO')", "count_vowels('sky')", "count_vowels('Aa')"], "Upper-case vowels are ignored.")
ex("logical_error", "medium", "Return the median of a non-empty list.",
   """
   def median(xs):
       values = sorted(xs)
       mid = len(values) // 2
       return values[mid]
   """, """
   def median(xs):
       values = sorted(xs)
       mid = len(values) // 2
       if len(values) % 2 == 0:
           return (values[mid - 1] + values[mid]) / 2
       return values[mid]
   """, ["median([3, 1, 2])", "median([4, 1, 3, 2])", "median([7])"], "Even-length lists need the mean of two values.")
ex("logical_error", "medium", "Return the list with consecutive duplicates removed.",
   """
   def dedupe_runs(xs):
       out = []
       for x in xs:
           if out and out[-1] == x:
               out.append(x)
           elif not out:
               out.append(x)
       return out
   """, """
   def dedupe_runs(xs):
       out = []
       for x in xs:
           if not out or out[-1] != x:
               out.append(x)
       return out
   """, ["dedupe_runs([1, 1, 2, 2, 1])", "dedupe_runs([])", "dedupe_runs([3])"], "Condition keeps duplicates instead.")
ex("logical_error", "hard", "Return True if brackets ()[]{} in s are balanced.",
   """
   def balanced(s):
       pairs = {")": "(", "]": "[", "}": "{"}
       stack = []
       for ch in s:
           if ch in "([{":
               stack.append(ch)
           elif ch in pairs:
               if not stack or stack.pop() != pairs[ch]:
                   return False
       return True
   """, """
   def balanced(s):
       pairs = {")": "(", "]": "[", "}": "{"}
       stack = []
       for ch in s:
           if ch in "([{":
               stack.append(ch)
           elif ch in pairs:
               if not stack or stack.pop() != pairs[ch]:
                   return False
       return not stack
   """, ["balanced('([]{})')", "balanced('(()')", "balanced(')(')", "balanced('')"],
   "Unclosed opening brackets are ignored at the end.")
ex("logical_error", "medium", "Return the list of numbers from 1 to n where multiples of 3 are 'Fizz', of 5 'Buzz', "
                              "of both 'FizzBuzz'.",
   """
   def fizzbuzz(n):
       out = []
       for i in range(1, n + 1):
           if i % 3 == 0:
               out.append("Fizz")
           elif i % 5 == 0:
               out.append("Buzz")
           elif i % 15 == 0:
               out.append("FizzBuzz")
           else:
               out.append(i)
       return out
   """, """
   def fizzbuzz(n):
       out = []
       for i in range(1, n + 1):
           if i % 15 == 0:
               out.append("FizzBuzz")
           elif i % 3 == 0:
               out.append("Fizz")
           elif i % 5 == 0:
               out.append("Buzz")
           else:
               out.append(i)
       return out
   """, ["fizzbuzz(15)[-1]", "fizzbuzz(5)", "fizzbuzz(0)"], "The FizzBuzz case is unreachable after the Fizz case.")
ex("logical_error", "medium", "Return a dict of word frequencies.",
   """
   def word_freq(text):
       freq = {}
       for word in text.split():
           freq[word] = 1
       return freq
   """, """
   def word_freq(text):
       freq = {}
       for word in text.split():
           freq[word] = freq.get(word, 0) + 1
       return freq
   """, ["word_freq('a b a')", "word_freq('')", "word_freq('x')"], "Counts are overwritten instead of incremented.")
ex("logical_error", "hard", "Merge two sorted lists into one sorted list.",
   """
   def merge(a, b):
       i = j = 0
       out = []
       while i < len(a) and j < len(b):
           if a[i] <= b[j]:
               out.append(a[i])
               i += 1
           else:
               out.append(b[j])
               j += 1
       return out
   """, """
   def merge(a, b):
       i = j = 0
       out = []
       while i < len(a) and j < len(b):
           if a[i] <= b[j]:
               out.append(a[i])
               i += 1
           else:
               out.append(b[j])
               j += 1
       out.extend(a[i:])
       out.extend(b[j:])
       return out
   """, ["merge([1, 4], [2, 3, 9])", "merge([], [1])", "merge([5], [])"], "Remaining elements are not appended.")
ex("logical_error", "medium", "Return the number of days in a month of a non-leap year (1-12).",
   """
   def days_in_month(m):
       if m == 2:
           return 28
       if m in (4, 6, 9):
           return 30
       return 31
   """, """
   def days_in_month(m):
       if m == 2:
           return 28
       if m in (4, 6, 9, 11):
           return 30
       return 31
   """, ["days_in_month(11)", "days_in_month(2)", "days_in_month(1)", "days_in_month(4)"],
   "November (11) is missing from the 30-day months.")
ex("logical_error", "easy", "Return the discounted price for a percentage discount, e.g. (200, 10) -> 180.0.",
   """
   def discounted(price, percent):
       return price - percent
   """, """
   def discounted(price, percent):
       return price * (1 - percent / 100)
   """, ["discounted(200, 10)", "discounted(50, 0)", "discounted(80, 50)"], "Subtracts the percentage as an amount.")
ex("logical_error", "medium", "Return True if all elements are unique.",
   """
   def all_unique(xs):
       return len(set(xs)) == len(xs) - 1
   """, """
   def all_unique(xs):
       return len(set(xs)) == len(xs)
   """, ["all_unique([1, 2, 3])", "all_unique([1, 1])", "all_unique([])"], "Off-by-one in the length comparison.")
ex("logical_error", "hard", "Rotate a list right by k positions.",
   """
   def rotate_right(xs, k):
       if not xs:
           return []
       k %= len(xs)
       return xs[k:] + xs[:k]
   """, """
   def rotate_right(xs, k):
       if not xs:
           return []
       k %= len(xs)
       return xs[-k:] + xs[:-k] if k else list(xs)
   """, ["rotate_right([1, 2, 3, 4], 1)", "rotate_right([1, 2, 3], 3)", "rotate_right([], 2)",
         "rotate_right([1, 2, 3], 4)"], "Slices implement a left rotation instead of a right rotation.")
ex("logical_error", "medium", "Return the sum of the digits of a non-negative integer.",
   """
   def digit_sum(n):
       total = 0
       while n > 0:
           total += n % 10
           n = n / 10
       return total
   """, """
   def digit_sum(n):
       total = 0
       while n > 0:
           total += n % 10
           n = n // 10
       return total
   """, ["digit_sum(123)", "digit_sum(0)", "digit_sum(9)"], "True division produces floats; use //.")
ex("logical_error", "medium", "Return the list of even numbers squared.",
   """
   def even_squares(xs):
       return [x * x for x in xs if x % 2]
   """, """
   def even_squares(xs):
       return [x * x for x in xs if x % 2 == 0]
   """, ["even_squares([1, 2, 3, 4])", "even_squares([])", "even_squares([0])"], "Condition selects odd numbers.")
ex("logical_error", "hard", "Return the length of the longest run of equal consecutive elements.",
   """
   def longest_run(xs):
       best = cur = 1
       for i in range(1, len(xs)):
           if xs[i] == xs[i - 1]:
               cur += 1
           else:
               cur = 1
       best = max(best, cur)
       return best if xs else 0
   """, """
   def longest_run(xs):
       best = cur = 1
       for i in range(1, len(xs)):
           if xs[i] == xs[i - 1]:
               cur += 1
           else:
               cur = 1
           best = max(best, cur)
       return best if xs else 0
   """, ["longest_run([1, 1, 1, 2])", "longest_run([1, 2, 2])", "longest_run([])", "longest_run([5])"],
   "Best is only updated after the loop instead of at every step.")
ex("logical_error", "medium", "Return the string with each word capitalised.",
   """
   def title_case(s):
       return " ".join(w.capitalize() for w in s.split(","))
   """, """
   def title_case(s):
       return " ".join(w.capitalize() for w in s.split())
   """, ["title_case('hello world')", "title_case('a')"], "Splits on commas instead of whitespace.")
ex("logical_error", "medium", "Return the minimum and maximum as a tuple (min, max).",
   """
   def min_max(xs):
       return (max(xs), min(xs))
   """, """
   def min_max(xs):
       return (min(xs), max(xs))
   """, ["min_max([3, 1, 2])", "min_max([5])"], "Tuple elements are swapped.")
ex("logical_error", "hard", "Return the number of ways to climb n stairs taking 1 or 2 steps.",
   """
   def climb(n):
       if n <= 1:
           return n
       return climb(n - 1) + climb(n - 2)
   """, """
   def climb(n):
       if n <= 1:
           return 1
       return climb(n - 1) + climb(n - 2)
   """, ["climb(0)", "climb(1)", "climb(4)", "climb(5)"], "Base case for n = 0 must be 1.")

# =============================================================================
# 7. Potential runtime exceptions
# =============================================================================
ex("potential_runtime_error", "easy", "Return the average of a list; return 0.0 for an empty list.",
   """
   def safe_average(values):
       return sum(values) / len(values)
   """, """
   def safe_average(values):
       if not values:
           return 0.0
       return sum(values) / len(values)
   """, ["safe_average([])", "safe_average([2, 4])"], "ZeroDivisionError on an empty list.")
ex("potential_runtime_error", "easy", "Return the value for key, or None when the key is missing.",
   """
   def lookup(d, key):
       return d[key]
   """, """
   def lookup(d, key):
       return d.get(key)
   """, ["lookup({'a': 1}, 'a')", "lookup({}, 'x')"], "KeyError for missing keys.")
ex("potential_runtime_error", "easy", "Return the first element, or None for an empty list.",
   """
   def first(xs):
       return xs[0]
   """, """
   def first(xs):
       return xs[0] if xs else None
   """, ["first([4, 5])", "first([])"], "IndexError on an empty list.")
ex("potential_runtime_error", "medium", "Convert a string to int, returning the default for invalid input.",
   """
   def to_int(text, default=0):
       return int(text)
   """, """
   def to_int(text, default=0):
       try:
           return int(text)
       except ValueError:
           return default
   """, ["to_int('42')", "to_int('abc')", "to_int('x', -1)"], "ValueError is not handled.")
ex("potential_runtime_error", "medium", "Return the length of the name, or 0 when name is None.",
   """
   def name_length(name):
       return len(name)
   """, """
   def name_length(name):
       return len(name) if name is not None else 0
   """, ["name_length('Ana')", "name_length(None)"], "TypeError when name is None.")
ex("potential_runtime_error", "medium", "Return the ratio a / b, or None when b is zero.",
   """
   def ratio(a, b):
       return a / b
   """, """
   def ratio(a, b):
       if b == 0:
           return None
       return a / b
   """, ["ratio(6, 3)", "ratio(1, 0)"], "ZeroDivisionError when b is zero.")
ex("potential_runtime_error", "medium", "Return pairs of adjacent elements.",
   """
   def adjacent_pairs(xs):
       return [(xs[i], xs[i + 1]) for i in range(len(xs))]
   """, """
   def adjacent_pairs(xs):
       return [(xs[i], xs[i + 1]) for i in range(len(xs) - 1)]
   """, ["adjacent_pairs([1, 2, 3])", "adjacent_pairs([])", "adjacent_pairs([1])"], "IndexError on the last index.")
ex("potential_runtime_error", "medium", "Return the nested value d['user']['name'] or 'unknown'.",
   """
   def user_name(d):
       return d["user"]["name"]
   """, """
   def user_name(d):
       return d.get("user", {}).get("name", "unknown")
   """, ["user_name({'user': {'name': 'Bo'}})", "user_name({})", "user_name({'user': {}})"], "KeyError for missing keys.")
ex("potential_runtime_error", "hard", "Return n factorial computed iteratively (must work for n up to 1500).",
   """
   def big_factorial(n):
       return 1 if n == 0 else n * big_factorial(n - 1)
   """, """
   def big_factorial(n):
       result = 1
       for i in range(2, n + 1):
           result *= i
       return result
   """, ["big_factorial(5)", "big_factorial(0)", "big_factorial(1500) % 1000003"],
   "Recursion exceeds the default recursion limit for large n (RecursionError).")
ex("potential_runtime_error", "medium", "Return the element at index i, or the default when out of range.",
   """
   def get_at(xs, i, default=None):
       return xs[i]
   """, """
   def get_at(xs, i, default=None):
       if -len(xs) <= i < len(xs):
           return xs[i]
       return default
   """, ["get_at([1, 2], 1)", "get_at([1, 2], 5)", "get_at([], 0, 'x')"], "IndexError for out-of-range indices.")
ex("potential_runtime_error", "medium", "Return the uppercase version of every string in the list, skipping None.",
   """
   def upper_all(items):
       return [item.upper() for item in items]
   """, """
   def upper_all(items):
       return [item.upper() for item in items if item is not None]
   """, ["upper_all(['a', None, 'b'])", "upper_all([])"], "AttributeError on None items.")
ex("potential_runtime_error", "medium", "Return the percentage of passed tests, 0.0 when there are none.",
   """
   def pass_percentage(passed, total):
       return round(100 * passed / total, 1)
   """, """
   def pass_percentage(passed, total):
       if total == 0:
           return 0.0
       return round(100 * passed / total, 1)
   """, ["pass_percentage(3, 4)", "pass_percentage(0, 0)"], "ZeroDivisionError when total is 0.")

# =============================================================================
# 8. Unreachable code / control-flow mistakes
# =============================================================================
ex("unreachable_code", "easy", "Return the list with every element doubled.",
   """
   def doubled(xs):
       out = []
       for x in xs:
           continue
           out.append(x * 2)
       return out
   """, """
   def doubled(xs):
       out = []
       for x in xs:
           out.append(x * 2)
       return out
   """, ["doubled([1, 2])", "doubled([])"], "Statement after 'continue' can never run.")
ex("unreachable_code", "easy", "Return the string stripped and lower-cased.",
   """
   def normalise(s):
       return s.strip()
       s = s.lower()
   """, """
   def normalise(s):
       return s.strip().lower()
   """, ["normalise('  HeLLo ')", "normalise('')"], "Lower-casing after return is unreachable.")
ex("unreachable_code", "medium", "Return the index of the first negative number, or -1.",
   """
   def first_negative(xs):
       for i, x in enumerate(xs):
           if x < 0:
               break
               return i
       return -1
   """, """
   def first_negative(xs):
       for i, x in enumerate(xs):
           if x < 0:
               return i
       return -1
   """, ["first_negative([3, -1, -2])", "first_negative([1, 2])", "first_negative([])"],
   "The return after break is unreachable.")
ex("unreachable_code", "medium", "Validate age: raise ValueError for negative ages, else return the age.",
   """
   def validate_age(age):
       if age < 0:
           return age
           raise ValueError("age must be non-negative")
       return age
   """, """
   def validate_age(age):
       if age < 0:
           raise ValueError("age must be non-negative")
       return age
   """, ["validate_age(30)", "validate_age(0)"], "raise after return is unreachable.",
   raises=[("validate_age(-1)", "ValueError")])
ex("unreachable_code", "medium", "Return the sum of positive numbers only.",
   """
   def positive_sum(xs):
       total = 0
       for x in xs:
           if x <= 0:
               continue
           else:
               continue
           total += x
       return total
   """, """
   def positive_sum(xs):
       total = 0
       for x in xs:
           if x <= 0:
               continue
           total += x
       return total
   """, ["positive_sum([1, -2, 3])", "positive_sum([])", "positive_sum([-1])"], "Accumulation is unreachable.")

# =============================================================================
# 9. Unused variables (computed value ignored)
# =============================================================================
ex("unused_variable", "easy", "Return the text without surrounding whitespace.",
   """
   def clean(text):
       stripped = text.strip()
       return text
   """, """
   def clean(text):
       stripped = text.strip()
       return stripped
   """, ["clean('  hi  ')", "clean('x')"], "The stripped value is computed but never used.")
ex("unused_variable", "medium", "Return the list sorted in descending order.",
   """
   def desc(xs):
       ordered = sorted(xs, reverse=True)
       return sorted(xs)
   """, """
   def desc(xs):
       ordered = sorted(xs, reverse=True)
       return ordered
   """, ["desc([1, 3, 2])", "desc([])"], "'ordered' is unused; the ascending list is returned.")
ex("unused_variable", "medium", "Return the price including 18% tax, rounded to 2 decimals.",
   """
   def with_tax(price):
       total = price * 1.18
       return round(price, 2)
   """, """
   def with_tax(price):
       total = price * 1.18
       return round(total, 2)
   """, ["with_tax(100)", "with_tax(0)", "with_tax(9.99)"], "The taxed total is never used.")
ex("unused_variable", "medium", "Return the username in lower case without spaces.",
   """
   def username(name):
       lowered = name.lower()
       return name.replace(" ", "")
   """, """
   def username(name):
       lowered = name.lower()
       return lowered.replace(" ", "")
   """, ["username('Ada Lovelace')", "username('BOB')"], "The lower-cased name is never used.")

# =============================================================================
# 10. Bad practices that cause observable bugs
# =============================================================================
ex("bad_practice", "medium", "Return a new list containing only the given item on every call without a list.",
   """
   def add_item(item, items=[]):
       items.append(item)
       return items
   """, """
   def add_item(item, items=None):
       if items is None:
           items = []
       items.append(item)
       return items
   """, ["(add_item(1), add_item(2))", "add_item(3, [0])"], "Mutable default argument is shared between calls.")
ex("bad_practice", "medium", "Return a dict counting items, starting fresh on each call.",
   """
   def tally(items, counts={}):
       for item in items:
           counts[item] = counts.get(item, 0) + 1
       return counts
   """, """
   def tally(items, counts=None):
       counts = {} if counts is None else counts
       for item in items:
           counts[item] = counts.get(item, 0) + 1
       return counts
   """, ["(tally(['a']), tally(['a']))", "tally([])"], "Mutable default dict accumulates between calls.")
ex("bad_practice", "medium", "Return True when the value is None, False otherwise (also for 0 and '').",
   """
   def is_missing(value):
       return not value
   """, """
   def is_missing(value):
       return value is None
   """, ["is_missing(None)", "is_missing(0)", "is_missing('')", "is_missing('x')"], "Truthiness treats 0 and '' as missing.")
ex("bad_practice", "medium", "Return a 3x3 grid of zeros where rows are independent lists.",
   """
   def zero_grid():
       grid = [[0] * 3] * 3
       grid[0][0] = 1
       return grid
   """, """
   def zero_grid():
       grid = [[0] * 3 for _ in range(3)]
       grid[0][0] = 1
       return grid
   """, ["zero_grid()", "zero_grid()[1]"], "[[0]*3]*3 repeats the same row object.")
ex("bad_practice", "hard", "Remove all even numbers from the list and return it.",
   """
   def remove_evens(xs):
       for x in xs:
           if x % 2 == 0:
               xs.remove(x)
       return xs
   """, """
   def remove_evens(xs):
       return [x for x in xs if x % 2 != 0]
   """, ["remove_evens([2, 4, 5, 6])", "remove_evens([1, 3])", "remove_evens([])"],
   "Modifying a list while iterating over it skips elements.")
ex("bad_practice", "medium", "Return True if two floats are equal within 1e-9.",
   """
   def almost_equal(a, b):
       return a == b
   """, """
   def almost_equal(a, b):
       return abs(a - b) <= 1e-9
   """, ["almost_equal(0.1 + 0.2, 0.3)", "almost_equal(1.0, 2.0)"], "Exact float comparison fails due to rounding.")
ex("bad_practice", "medium", "Return a copy of the list with x appended, leaving the original unchanged.",
   """
   def appended_copy(xs, x):
       copy = xs
       copy.append(x)
       return copy
   """, """
   def appended_copy(xs, x):
       copy = list(xs)
       copy.append(x)
       return copy
   """, ["(lambda base: (appended_copy(base, 9), base))([1, 2])",
         "(lambda base: (appended_copy(base, 'x'), base))([])"], "Assignment aliases the list instead of copying it.")
ex("bad_practice", "medium", "Return a list of functions where the i-th returns i (for i in 0..2).",
   """
   def make_getters():
       return [lambda: i for i in range(3)]
   """, """
   def make_getters():
       return [lambda i=i: i for i in range(3)]
   """, ["[f() for f in make_getters()]", "make_getters()[0]()"], "Late binding: every lambda sees the final value of i.")
ex("bad_practice", "medium", "Return the string repeated n times separated by commas.",
   """
   def repeat_csv(s, n):
       out = ""
       for _ in range(n):
           out += s + ","
       return out
   """, """
   def repeat_csv(s, n):
       return ",".join([s] * n)
   """, ["repeat_csv('a', 3)", "repeat_csv('x', 0)", "repeat_csv('b', 1)"],
   "Trailing comma; quadratic concatenation in a loop.")

# =============================================================================
# 11. Mixed / algorithmic bugs (medium–hard)
# =============================================================================
ex("logical_error", "hard", "Sort a list using bubble sort and return it.",
   """
   def bubble_sort(xs):
       xs = list(xs)
       n = len(xs)
       for i in range(n):
           for j in range(n - i - 2):
               if xs[j] > xs[j + 1]:
                   xs[j], xs[j + 1] = xs[j + 1], xs[j]
       return xs
   """, """
   def bubble_sort(xs):
       xs = list(xs)
       n = len(xs)
       for i in range(n):
           for j in range(n - i - 1):
               if xs[j] > xs[j + 1]:
                   xs[j], xs[j + 1] = xs[j + 1], xs[j]
       return xs
   """, ["bubble_sort([3, 1, 2])", "bubble_sort([2, 1])", "bubble_sort([])", "bubble_sort([5, 4, 3, 2, 1])"],
   "Inner range stops one element too early.")
ex("logical_error", "hard", "Return the greatest common divisor using Euclid's algorithm.",
   """
   def euclid(a, b):
       while b:
           a, b = b, a // b
       return a
   """, """
   def euclid(a, b):
       while b:
           a, b = b, a % b
       return a
   """, ["euclid(48, 18)", "euclid(7, 3)", "euclid(10, 0)"], "Uses integer division instead of modulo.")
ex("logical_error", "hard", "Return the list flattened one level deep.",
   """
   def flatten(nested):
       out = []
       for sub in nested:
           out.append(sub)
       return out
   """, """
   def flatten(nested):
       out = []
       for sub in nested:
           out.extend(sub)
       return out
   """, ["flatten([[1, 2], [3]])", "flatten([])", "flatten([[], [4]])"], "append adds the sub-list instead of its items.")
ex("logical_error", "medium", "Return True if the two strings are anagrams (ignore case).",
   """
   def anagrams(a, b):
       return set(a.lower()) == set(b.lower())
   """, """
   def anagrams(a, b):
       return sorted(a.lower()) == sorted(b.lower())
   """, ["anagrams('Listen', 'Silent')", "anagrams('aab', 'abb')", "anagrams('', '')"], "Sets ignore letter counts.")
ex("logical_error", "medium", "Return the number of words in the sentence.",
   """
   def word_count(sentence):
       return len(sentence.split(" "))
   """, """
   def word_count(sentence):
       return len(sentence.split())
   """, ["word_count('a  b')", "word_count('')", "word_count('one')"], "split(' ') counts empty strings.")
ex("logical_error", "hard", "Return the matrix transposed.",
   """
   def transpose(m):
       return [[m[i][j] for i in range(len(m[0]))] for j in range(len(m))]
   """, """
   def transpose(m):
       return [[m[i][j] for i in range(len(m))] for j in range(len(m[0]))]
   """, ["transpose([[1, 2, 3], [4, 5, 6]])", "transpose([[1]])"], "Row and column ranges are swapped.")
ex("logical_error", "medium", "Return the compound amount P*(1+r/100)**years rounded to 2 decimals.",
   """
   def compound(principal, rate, years):
       return round(principal * (1 + rate / 100) * years, 2)
   """, """
   def compound(principal, rate, years):
       return round(principal * (1 + rate / 100) ** years, 2)
   """, ["compound(1000, 10, 2)", "compound(500, 0, 3)", "compound(100, 5, 0)"], "Multiplication instead of power.")
ex("logical_error", "medium", "Return the list of indexes where value occurs.",
   """
   def find_all(xs, value):
       return [i for i, x in enumerate(xs) if x is value]
   """, """
   def find_all(xs, value):
       return [i for i, x in enumerate(xs) if x == value]
   """, ["find_all([1000, 5, 1000], int('1000'))", "find_all([], 1)", "find_all(['a', 'b'], 'b')"],
   "'is' compares identity instead of equality.")
ex("logical_error", "medium", "Clamp x into the inclusive range [low, high].",
   """
   def clamp(x, low, high):
       return max(high, min(low, x))
   """, """
   def clamp(x, low, high):
       return max(low, min(high, x))
   """, ["clamp(5, 0, 10)", "clamp(-3, 0, 10)", "clamp(42, 0, 10)"], "low and high are swapped.")
ex("logical_error", "hard", "Return the run-length encoding as a list of (char, count) pairs.",
   """
   def rle(s):
       if not s:
           return []
       out = []
       current, count = s[0], 1
       for ch in s[1:]:
           if ch == current:
               count += 1
           else:
               out.append((current, count))
               current, count = ch, 1
       return out
   """, """
   def rle(s):
       if not s:
           return []
       out = []
       current, count = s[0], 1
       for ch in s[1:]:
           if ch == current:
               count += 1
           else:
               out.append((current, count))
               current, count = ch, 1
       out.append((current, count))
       return out
   """, ["rle('aaabcc')", "rle('')", "rle('z')"], "The final run is never appended.")
ex("logical_error", "medium", "Return the BMI weight / height**2 rounded to 1 decimal.",
   """
   def bmi(weight, height):
       return round(weight / height * 2, 1)
   """, """
   def bmi(weight, height):
       return round(weight / height ** 2, 1)
   """, ["bmi(70, 1.75)", "bmi(50, 1.6)"], "'* 2' instead of '** 2'.")
ex("logical_error", "medium", "Return True if year-month-day string 'YYYY-MM-DD' has a valid month (1-12).",
   """
   def valid_month(date):
       month = int(date.split("-")[2])
       return 1 <= month <= 12
   """, """
   def valid_month(date):
       month = int(date.split("-")[1])
       return 1 <= month <= 12
   """, ["valid_month('2024-13-01')", "valid_month('2024-02-30')", "valid_month('2024-12-12')"],
   "Uses the day field instead of the month field.")
ex("type_issue", "medium", "Return the total cost of items given as (name, price) tuples.",
   """
   def total_cost(items):
       return sum(items)
   """, """
   def total_cost(items):
       return sum(price for _name, price in items)
   """, ["total_cost([('a', 2.5), ('b', 1.5)])", "total_cost([])"], "Cannot sum tuples with an int start value.")
ex("potential_runtime_error", "hard", "Return the average word length of a sentence, 0.0 for no words.",
   """
   def avg_word_length(sentence):
       words = sentence.split()
       return sum(len(w) for w in words) / len(words)
   """, """
   def avg_word_length(sentence):
       words = sentence.split()
       if not words:
           return 0.0
       return sum(len(w) for w in words) / len(words)
   """, ["avg_word_length('ab abcd')", "avg_word_length('   ')"], "ZeroDivisionError for blank sentences.")
ex("undefined_variable", "hard", "Return the count of each word, using a helper normalise function.",
   """
   def count_words(text):
       counts = {}
       for word in text.split():
           key = normalise(word)
           counts[key] = counts.get(key, 0) + 1
       return counts
   """, """
   def normalise(word):
       return word.strip(".,!?").lower()


   def count_words(text):
       counts = {}
       for word in text.split():
           key = normalise(word)
           counts[key] = counts.get(key, 0) + 1
       return counts
   """, ["count_words('Hi hi, there!')", "count_words('')"], "Helper function 'normalise' is not defined.")


# =============================================================================
# Builder
# =============================================================================
_RUNNER = r'''
import json, sys
src = open(sys.argv[1], encoding="utf-8").read()
calls = json.loads(open(sys.argv[2], encoding="utf-8").read())
ns = {}
out = {"import_error": None, "values": []}
try:
    exec(compile(src, "solution.py", "exec"), ns)
except BaseException as exc:
    out["import_error"] = type(exc).__name__
for call in calls:
    if out["import_error"]:
        out["values"].append({"error": out["import_error"]})
        continue
    try:
        value = eval(call, ns)
        out["values"].append({"repr": repr(value)})
    except BaseException as exc:
        out["values"].append({"error": type(exc).__name__})
print(json.dumps(out))
'''


def run_calls(code: str, calls: list[str]) -> dict:
    """Run trusted dataset code in a subprocess and return repr()s or exception names."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "src.py").write_text(code, encoding="utf-8")
        (base / "calls.json").write_text(json.dumps(calls), encoding="utf-8")
        (base / "runner.py").write_text(_RUNNER, encoding="utf-8")
        done = subprocess.run([sys.executable, "-I", str(base / "runner.py"), str(base / "src.py"),
                               str(base / "calls.json")], capture_output=True, text=True, timeout=30, cwd=tmp,
                              check=False)
    if done.returncode != 0:
        raise RuntimeError(done.stderr)
    return json.loads(done.stdout)


def bug_lines(buggy: str, fixed: str) -> list[int]:
    """1-based line numbers in the buggy program that differ from the fix."""
    a, b = buggy.splitlines(), fixed.splitlines()
    lines: set[int] = set()
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            lines.update(range(i1 + 1, i2 + 1))
        elif tag == "insert":
            lines.add(min(max(i1, 1), len(a)))
    return sorted(lines)


def build() -> list[dict]:
    dataset = []
    for index, example in enumerate(EXAMPLES, start=1):
        calls = example["calls"]
        raise_calls = [c for c, _ in example["raises"]]
        ref = run_calls(example["fixed_code"], calls + raise_calls)
        if ref["import_error"]:
            raise SystemExit(f"Example {index}: reference solution fails to load ({ref['import_error']})")
        tests = []
        for call, outcome in zip(calls, ref["values"][:len(calls)]):
            if "error" in outcome:
                raise SystemExit(f"Example {index}: reference raised {outcome['error']} for {call}")
            tests.append({"call": call, "expected": outcome["repr"], "expects_exception": ""})
        for (call, exc_name), outcome in zip(example["raises"], ref["values"][len(calls):]):
            if outcome.get("error") != exc_name:
                raise SystemExit(f"Example {index}: reference did not raise {exc_name} for {call}")
            tests.append({"call": call, "expected": "", "expects_exception": exc_name})

        buggy = run_calls(example["buggy_code"], [t["call"] for t in tests])
        failing = 0
        for test, outcome in zip(tests, buggy["values"]):
            if test["expects_exception"]:
                failing += outcome.get("error") != test["expects_exception"]
            else:
                failing += outcome.get("repr") != test["expected"]
        if failing == 0:
            raise SystemExit(f"Example {index}: bug is not observable by its tests")

        if len(tests) < 2:
            raise SystemExit(f"Example {index}: needs at least 2 tests (validation + held-out)")
        entry = example["fixed_code"].split("def ", 1)[1].split("(", 1)[0] if "def " in example["fixed_code"] else ""
        n_valid = max(1, len(tests) // 2)
        dataset.append({
            "id": f"CM{index:03d}",
            "split": "dev" if index % 4 == 0 else "eval",
            "category": example["category"],
            "difficulty": example["difficulty"],
            "intended_behavior": example["intended_behavior"],
            "buggy_code": example["buggy_code"],
            "fixed_code": example["fixed_code"],
            "entry_point": entry,
            "bug_lines": bug_lines(example["buggy_code"], example["fixed_code"]),
            "validation_tests": tests[:n_valid],
            "heldout_tests": tests[n_valid:],
            "expected_output": tests[0]["expected"],
            "buggy_failing_tests": failing,
            "error_explanation": example["explanation"],
            "source": "CodeMind AI custom dataset (original examples)",
        })
    return dataset


def main() -> None:
    dataset = build()
    categories: dict[str, int] = {}
    for item in dataset:
        categories[item["category"]] = categories.get(item["category"], 0) + 1
    payload = {
        "name": "CodeMind AI custom Python bug benchmark",
        "version": "1.0",
        "license": "MIT (same as the project); all programs written for this project",
        "description": "Small single-function Python programs with one injected bug each, a reference fix, intended "
                       "behaviour and independent tests. Expected values are computed from the reference solution.",
        "split_policy": "Deterministic: every 4th example is 'dev' (prompt tuning), the rest are 'eval' (reporting).",
        "test_policy": "validation_tests may be shown to the repair loop; heldout_tests are used only for scoring.",
        "counts": {"total": len(dataset), "dev": sum(d["split"] == "dev" for d in dataset),
                   "eval": sum(d["split"] == "eval" for d in dataset), "by_category": categories},
        "examples": dataset,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset)} verified examples to {OUT}")
    print(json.dumps(payload["counts"], indent=2))


if __name__ == "__main__":
    main()
