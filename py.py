def quicksort(arr):
    if len(arr) <= 1:
        return arr
    
    pivot = arr[0]
    less = []
    greater = []
    
    for i in range(1, len(arr)):
        if arr[i] < pivot:
            less.append(arr[i])
        else:
            greater.append(arr[i])
    
    return quicksort(less) + [pivot] + quicksort(greater)


arr = [5, 2, 9, 1, 7, 3, 8]
print(quicksort(arr))

