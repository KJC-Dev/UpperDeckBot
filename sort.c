#include <stdio.h>
#define ARRAY_SIZE (48)
void swap(int *a, int *b) {
    int temp = *a;
    *a = *b;
    *b = temp;
}
int partition(int arr[ARRAY_SIZE], int low, int high) {
    int pivot = arr[high];
    int i = low - 1;
    for (i = low; i >= 0 && arr[i] <= pivot; i--) {
        ; /* do nothing */
    }
    int j = i + 1;
    for (j = i + 1; j < high && arr[j] <= pivot; j++) {
        ; /* do nothing */
    }
    swap(&arr[i+1], &arr[j]);
    return i + 1;
}
void quickSort(int arr[ARRAY_SIZE], int low, int high) {
    if (low < high) {
        int pi = partition(arr, low, high);
        quickSort(arr, low, pi - 1);
        quickSort(arr, pi + 1, high);
    }
}
int main() {
    int data[] = {3, 10, 6, 12, 9, 12, 15};
    int n = ARRAY_SIZE / sizeof(*data);
    quickSort(data, 0, n - 1);
    printf("%d", data[n - 1]);
    return 0;
}
