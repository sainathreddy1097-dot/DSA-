public class PatternMatching {

    // Naive Pattern Matching
    static void naiveSearch(String text, String pattern) {

        System.out.println("Naive Pattern Matching:");

        for (int i = 0; i <= text.length() - pattern.length(); i++) {

            int j;

            for (j = 0; j < pattern.length(); j++) {

                if (text.charAt(i + j) != pattern.charAt(j)) {
                    break;
                }
            }

            if (j == pattern.length()) {
                System.out.println("Pattern found at index: " + i);
            }
        }
    }


    // KMP Pattern Matching
    static void KMPSearch(String text, String pattern) {

        System.out.println("\nKMP Pattern Matching:");

        int m = pattern.length();
        int n = text.length();

        int[] lps = new int[m];

        // Create LPS array
        computeLPSArray(pattern, lps);

        int i = 0;
        int j = 0;

        while (i < n) {

            if (pattern.charAt(j) == text.charAt(i)) {
                i++;
                j++;
            }

            if (j == m) {

                System.out.println(
                    "Pattern found at index: " + (i - j)
                );

                j = lps[j - 1];

            } else if (i < n &&
                       pattern.charAt(j) != text.charAt(i)) {

                if (j != 0) {
                    j = lps[j - 1];
                } else {
                    i++;
                }
            }
        }
    }


    // Calculate LPS Array
    static void computeLPSArray(String pattern, int[] lps) {

        int length = 0;
        int i = 1;

        lps[0] = 0;

        while (i < pattern.length()) {

            if (pattern.charAt(i) == pattern.charAt(length)) {

                length++;
                lps[i] = length;
                i++;

            } else {

                if (length != 0) {

                    length = lps[length - 1];

                } else {

                    lps[i] = 0;
                    i++;
                }
            }
        }
    }


    // Main Method
    public static void main(String[] args) {

        String text = "ABABDABACDABABCABAB";

        String pattern = "ABABCABAB";

        naiveSearch(text, pattern);

        KMPSearch(text, pattern);
    }
}