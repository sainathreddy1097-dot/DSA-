# ==============================================================================
# Practical 4: Implementation of Rabin–Karp Algorithm and Document Similarity
#              Analysis using Suffix-Based Processing
# Course Outcome: CO2
# Aim: To implement Rabin-Karp algorithm for pattern matching and analyze
#      document similarity.
# ==============================================================================

import os

script_dir = os.path.dirname(os.path.abspath(__file__))

# Read text for Rabin-Karp
sample_path = os.path.join(script_dir, "sample.txt")
with open(sample_path, "r") as file:
    text = file.read().strip()

pattern = input("Enter Pattern: ")

print("\nRabin-Karp Result")
print("-----------------")

# Simple Rabin-Karp using Python hash
m = len(pattern)
pattern_hash = hash(pattern)

for i in range(len(text) - m + 1):
    window = text[i:i + m]
    if hash(window) == pattern_hash:
        if window == pattern:
            print("Pattern found at index", i)

# Document Similarity
doc1_path = os.path.join(script_dir, "doc1.txt")
doc2_path = os.path.join(script_dir, "doc2.txt")

with open(doc1_path, "r") as f1:
    doc1 = f1.read().lower().split()

with open(doc2_path, "r") as f2:
    doc2 = f2.read().lower().split()

common_suffix_words = set(doc1).intersection(set(doc2))
print("\nCommon Words")
print(common_suffix_words)

similarity = (len(common_suffix_words) / len(set(doc1).union(set(doc2)))) * 100
print("Similarity = {:.2f}%".format(similarity))
