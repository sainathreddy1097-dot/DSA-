# ==============================================================================
# Practical 3: Naïve Pattern Matching & KMP Algorithm
# Course Outcome: CO2
# Aim: To implement Naïve Pattern Matching and Knuth–Morris–Pratt (KMP)
#      algorithms for keyword searching.
# ==============================================================================

import os

# Read text from file
script_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(script_dir, "sample.txt")

with open(file_path, "r") as file:
    text = file.read().strip()

# Get pattern from user
pattern = input("Enter Pattern: ")

print("\nNaive Pattern Matching Result")
print("-----------------------------")
# Naive Pattern Matching
for i in range(len(text) - len(pattern) + 1):
    if text[i:i + len(pattern)] == pattern:
        print("Pattern found at index", i)


# KMP Functions
def compute_lps(pattern):
    lps = [0] * len(pattern)
    length = 0
    i = 1
    while i < len(pattern):
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        else:
            if length != 0:
                length = lps[length - 1]
            else:
                lps[i] = 0
                i += 1
    return lps


def kmp_search(text, pattern):
    lps = compute_lps(pattern)
    i = j = 0
    print("\nKMP Result")
    print("----------")
    while i < len(text):
        if pattern[j] == text[i]:
            i += 1
            j += 1
        if j == len(pattern):
            print("Pattern found at index", i - j)
            j = lps[j - 1]
        elif i < len(text) and pattern[j] != text[i]:
            if j != 0:
                j = lps[j - 1]
            else:
                i += 1


kmp_search(text, pattern)
