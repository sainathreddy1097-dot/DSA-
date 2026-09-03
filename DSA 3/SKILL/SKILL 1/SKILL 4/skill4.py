# =====================================================
# EVALUATING SEARCH-PROCESSING REQUIREMENTS
# AND ALGORITHM SELECTION STRATEGIES
# =====================================================

print("========== SEARCH ALGORITHM SELECTION ==========")

print("\nSelect the Search Requirement:")

print("1. Small or Unsorted Dataset")
print("2. Large and Sorted Dataset")
print("3. Simple Text Pattern Search")
print("4. Large Text with Efficient Pattern Matching")
print("5. Approximate or Fuzzy Search")

choice = int(input("\nEnter your choice (1-5): "))


# SMALL OR UNSORTED DATASET
if choice == 1:

    print("\nRecommended Algorithm: Linear Search")
    print("Reason: The dataset is small or unsorted.")
    print("Time Complexity: O(n)")
    print("Example: Searching for a student name in a small list.")


# LARGE AND SORTED DATASET
elif choice == 2:

    print("\nRecommended Algorithm: Binary Search")
    print("Reason: Binary Search works efficiently on sorted data.")
    print("Time Complexity: O(log n)")
    print("Example: Searching for a roll number in a sorted list.")


# SIMPLE TEXT SEARCH
elif choice == 3:

    print("\nRecommended Algorithm: Naive Pattern Matching")
    print("Reason: Suitable for simple pattern searching.")
    print("Example: Searching for a word in a small document.")


# LARGE TEXT SEARCH
elif choice == 4:

    print("\nRecommended Algorithm: KMP Algorithm")
    print("Reason: KMP avoids unnecessary repeated comparisons.")
    print("Time Complexity: O(n + m)")
    print("Example: Searching for a keyword in a large text file.")


# APPROXIMATE SEARCH
elif choice == 5:

    print("\nRecommended Algorithm: Edit Distance / Fuzzy Search")
    print("Reason: It finds similar words even when spelling is different.")
    print("Example: Searching for 'pythn' and finding 'python'.")


# INVALID INPUT
else:

    print("\nInvalid Choice!")