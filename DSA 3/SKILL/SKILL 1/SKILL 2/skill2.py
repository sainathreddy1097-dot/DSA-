# MAPPING COMPUTATIONAL PROBLEMS
# TO ALGORITHMIC PARADIGMS

print("========== ALGORITHMIC PARADIGM MAPPING ==========")

print("\n1. Searching Problem")
print("2. Sorting Problem")
print("3. Optimization Problem")
print("4. Repeated Subproblem Problem")
print("5. Constraint Satisfaction Problem")

choice = int(input("\nEnter your choice (1-5): "))

if choice == 1:
    print("\nProblem: Searching")
    print("Suitable Paradigm: Brute Force / Divide and Conquer")
    print("Example Algorithm: Linear Search or Binary Search")

elif choice == 2:
    print("\nProblem: Sorting")
    print("Suitable Paradigm: Divide and Conquer")
    print("Example Algorithm: Merge Sort")

elif choice == 3:
    print("\nProblem: Optimization")
    print("Suitable Paradigm: Greedy Method")
    print("Example Algorithm: Activity Selection")

elif choice == 4:
    print("\nProblem: Repeated Subproblems")
    print("Suitable Paradigm: Dynamic Programming")
    print("Example Algorithm: Fibonacci")

elif choice == 5:
    print("\nProblem: Constraint Satisfaction")
    print("Suitable Paradigm: Backtracking")
    print("Example Algorithm: N-Queens Problem")

else:
    print("\nInvalid Choice!")