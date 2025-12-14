from storix import LocalFilesystem


# from storix.core import wc

fs = LocalFilesystem(initialpath='..')

# print(fs.find("."))
# res = fs.find(".") | wc
# print(res)
# print(fs.tree("."))
t = fs.tree('.', abs=False)

print(t)
print(f'size: {t.size}')
# # check built caching working
# for _ in range(int(1e4 * 10)):
#     t.build()
