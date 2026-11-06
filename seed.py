"""Seed Firestore with store settings, model v1 and a demo menu. Safe to re-run: existing data is kept."""
from connect import db
from data import DEFAULT_SETTINGS, save_settings, seed_model_v1

PRODUCTS = [
    ('Pad Thai with Shrimp', 'Noodles', 120, 'Rice noodles, tamarind, peanuts, bean sprouts'),
    ('Pad See Ew', 'Noodles', 100, 'Wide noodles, soy sauce, Chinese broccoli'),
    ('Boat Noodle Soup', 'Noodles', 90, 'Rich pork broth with herbs'),
    ('Khao Man Gai', 'Rice', 80, 'Poached chicken on garlic rice, ginger sauce'),
    ('Basil Pork with Fried Egg', 'Rice', 90, 'Pad kra pao, spicy'),
    ('Green Curry Chicken', 'Curry', 140, 'With jasmine rice'),
    ('Massaman Beef', 'Curry', 180, 'Slow-cooked beef, potato, peanuts'),
    ('Som Tam', 'Salad', 70, 'Green papaya salad'),
    ('Larb Moo', 'Salad', 90, 'Spicy minced pork salad with herbs'),
    ('Mango Sticky Rice', 'Dessert', 90, 'Seasonal mango, coconut cream'),
    ('Thai Iced Tea', 'Drinks', 50, 'Sweet milk tea'),
    ('Fresh Coconut', 'Drinks', 60, 'Chilled whole coconut'),
]


def main():
    if not db.collection('settings').document('store').get().exists:
        save_settings(DEFAULT_SETTINGS)
        print('settings/store created')
    seed_model_v1()
    print('models/v1 ready')
    if not list(db.collection('products').limit(1).stream()):
        for name, category, price, description in PRODUCTS:
            db.collection('products').document().set({
                'name': name, 'category': category, 'price': price, 'description': description,
                'image_url': '', 'hidden': False,
            })
        print(f'{len(PRODUCTS)} products created')
    else:
        print('products already exist, skipped')


if __name__ == '__main__':
    main()
