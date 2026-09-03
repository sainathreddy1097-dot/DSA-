# ==================================================
# ANALYSIS OF TEXTHACK WORKFLOW
# AND PROCESSING COMPONENT INTERACTION
# ==================================================

# COMPONENT 1: DOCUMENT LOADING

documents = [
    "Python is used for Data Science and Machine Learning.",
    "Text Analytics helps in processing and analysing text.",
    "Machine Learning is a part of Artificial Intelligence.",
    "Data Science uses programming and statistical methods."
]

print("========== TEXTHACK WORKFLOW ==========")

print("\nSTEP 1: DOCUMENT LOADING")

for i in range(len(documents)):
    print("Document", i + 1, ":", documents[i])


# COMPONENT 2: TEXT PREPROCESSING

print("\nSTEP 2: TEXT PREPROCESSING")

processed_documents = []

for document in documents:

    processed_text = document.lower()

    processed_documents.append(processed_text)

print("Documents converted to lowercase successfully.")


# COMPONENT 3: ARTICLE REPOSITORY

print("\nSTEP 3: ARTICLE REPOSITORY")

repository = processed_documents

print("Total documents stored:", len(repository))


# COMPONENT 4: USER QUERY

print("\nSTEP 4: USER QUERY")

query = input("Enter your search query: ")


# COMPONENT 5: QUERY PROCESSING

print("\nSTEP 5: QUERY PROCESSING")

processed_query = query.lower()

print("Processed Query:", processed_query)


# COMPONENT 6: SEARCH ENGINE

print("\nSTEP 6: SEARCH ENGINE")

results = []

for i in range(len(repository)):

    if processed_query in repository[i]:

        results.append(i)


# COMPONENT 7 AND 8: RESULT RETRIEVAL AND DISPLAY

print("\nSTEP 7: RESULT RETRIEVAL")

if len(results) > 0:

    print("\nMatching Documents:")

    for index in results:

        print("Document", index + 1, ":", documents[index])

else:

    print("No matching documents found.")
    