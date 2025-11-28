from storix import AzureDataLake


# from storix.core import wc

fs = AzureDataLake()  # noqa: F821
# print(fs.pwd())
fs.cd('user')

# print(fs.find("."))
# res = fs.find(".") | wc
# print(res)
# print(fs.tree("."))
t = fs.tree('.')

print(t)
# try exhaustion
print(t.size)
print(t.size)

print(len(t))
assert len(t) == t.size

# check built caching working
for _ in range(int(1e4 * 10)):
    t.build()
