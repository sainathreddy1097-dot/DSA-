# ==============================================================================
# Practical 2: Query Processing and Article Retrieval Framework Implementation
# Course Outcome: CO1
# Aim: To implement query processing and article retrieval using Python.
# ==============================================================================

import os

# Open the article repository
script_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(script_dir, "articles.txt")

with open(file_path, "r") as file:
    # Read all articles
    articles = file.readlines()

# Get keyword from user
query = input("Enter keyword: ")

print("\nMatching Articles")
print("---------------------------")
found = False

# Search each article
for article in articles:
    if query.lower() in article.lower():
        print(article.strip())
        found = True

# If no article matches
if not found:
    print("No matching article found.")
