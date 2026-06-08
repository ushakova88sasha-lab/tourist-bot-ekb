import json, sys
sys.path.insert(0, r"D:\tourist_bot")

with open(r"D:\tourist_bot\data\points.json", encoding="utf-8") as f:
    import bot
    bot.POINTS = json.load(f)

point, dist = bot.find_nearest_point(56.83900, 60.60580)
print(f"Тест 1 (в 10 м):   {point['name'] if point else 'не найдено'}, {dist:.0f} м")

point2, dist2 = bot.find_nearest_point(56.84050, 60.60700)
print(f"Тест 2 (в ~200 м):  {point2['name'] if point2 else 'не найдено'}, {dist2:.0f} м")

point3, dist3 = bot.find_nearest_point(56.84300, 60.61200)
print(f"Тест 3 (в ~650 м):  {'найдено' if point3 else 'не найдено'}, ближайшее в {dist3:.0f} м")
