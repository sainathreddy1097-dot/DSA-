# TEXT ANALYTICS SYSTEM AND QUERY CATEGORIES
# Skill 1 - TextHack

# Create an article repository
articles = [
    "Python is widely used for Data Science and Machine Learning.",
    "Machine Learning is an important area of Artificial Intelligence.",
    "Text Analytics helps in processing and analysing textual data.",
    "Python programming is useful for Artificial Intelligence applications.",
    "Data Science uses statistics, programming and Machine Learning."
]

# Display articles
print("========== TEXT HACK ARTICLE REPOSITORY ==========")

for i in range(len(articles)):
    print("Article", i + 1, ":", articles[i])

# Display query categories
print("\n========== QUERY CATEGORIES ==========")
print("1. Single Keyword Search")
print("2. Multi-Keyword Search")
print("3. Exact Phrase Search")

# Get user choice
choice = int(input("\nEnter your choice (1-3): "))

# Get search query
query = input("Enter your search query: ")
query = query.lower()

found = False

# -------------------------------
# 1. Single Keyword Search
# -------------------------------
if choice == 1:
    print("\n========== SEARCH RESULTS ==========")

    for i in range(len(articles)):
        if query in articles[i].lower():
            print("\nArticle", i + 1, ":", articles[i])
            found = True

# -------------------------------
# 2. Multi-Keyword Search
# -------------------------------
elif choice == 2:
    print("\n========== SEARCH RESULTS ==========")

    keywords = query.split()

    for i in range(len(articles)):
        article = articles[i].lower()
        match = True

        for word in keywords:
            if word not in article:
                match = False

        if match:
            print("\nArticle", i + 1, ":", articles[i])
            found = True

# -------------------------------
# 3. Exact Phrase Search
# -------------------------------
elif choice == 3:
    print("\n========== SEARCH RESULTS ==========")

    for i in range(len(articles)):
        article = articles[i].lower()

        if query in article:
            print("\nArticle", i + 1, ":", articles[i])
            found = True

# Invalid choice
else:
    print("\nInvalid choice!")

# -------------------------------
# No results message
# -------------------------------
if choice >= 1 and choice <= 3 and found == False:
    print("\nNo matching articles found.")