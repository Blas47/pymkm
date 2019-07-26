#!/usr/bin/env python3
"""
The PyMKM example app.
"""

__author__ = "Andreas Ehrlund"
__version__ = "1.0.5"
__license__ = "MIT"

import csv
import json
import logging
import math
import os.path
import pprint
import sys

import progressbar
import tabulate as tb

from pymkm_helper import PyMkmHelper
from pymkmapi import PyMkmApi, api_wrapper
from micro_menu import *


class PyMkmApp:
    logging.basicConfig(stream=sys.stderr, level=logging.WARN)

    def __init__(self, config=None):
        if (config == None):
            logging.debug(">> Loading config file")
            try:
                self.config = json.load(open('config.json'))
            except FileNotFoundError:
                logging.error(
                    "You must copy config_template.json to config.json and populate the fields.")
                sys.exit(0)
        else:
            self.config = config

        self.api = PyMkmApi(config=self.config)

    def start(self):
        menu = MicroMenu(f"PyMKM {__version__}")

        menu.add_function_item("Update stock prices",
                               self.update_stock_prices_to_trend, {
                                   'api': self.api}
                               )
        menu.add_function_item("Update price for a card",
                               self.update_product_to_trend, {'api': self.api}
                               )
        menu.add_function_item("List competition for a card",
                               self.list_competition_for_product, {
                                   'api': self.api}
                               )
        menu.add_function_item("Show top 20 expensive items in stock",
                               self.show_top_expensive_articles_in_stock, {
                                   'num_articles': 20, 'api': self.api}
                               )
        menu.add_function_item("Show account info",
                               self.show_account_info, {'api': self.api}
                               )
        menu.add_function_item("Clear entire stock (WARNING)",
                               self.clear_entire_stock, {'api': self.api}
                               )
        menu.add_function_item("Import stock from .\list.csv",
                               self.import_from_csv, {'api': self.api}
                               )

        menu.show()

    @api_wrapper
    def update_stock_prices_to_trend(self, api):
        ''' This function updates all prices in the user's stock to TREND. '''

        uploadable_json = self.calculate_new_prices_for_stock(api=self.api)

        if len(uploadable_json) > 0:

            self.display_price_changes_table(uploadable_json)

            if PyMkmHelper.prompt_bool("Do you want to update these prices?") == True:
                # Update articles on MKM
                api.set_stock(uploadable_json)
                print('Prices updated.')
            else:
                print('Prices not updated.')
        else:
            print('No prices to update.')

    @api_wrapper
    def update_product_to_trend(self, api):
        ''' This function updates one product in the user's stock to TREND. '''
        search_string = PyMkmHelper.prompt_string('Search card name')

        try:
            articles = api.find_stock_article(search_string, 1)
        except Exception as err:
            print(err)

        if len(articles) > 1:
            article = self.select_from_list_of_articles(articles)
        else:
            article = articles[0]
            print('Found: {} [{}].'.format(article['product']
                                           ['enName'], article['product']['expansion']))
        r = self.get_price_for_single_article(article, api=self.api)

        if r:
            self.draw_price_changes_table([r])

            print('\nTotal price difference: {}.'.format(
                str(round(sum(item['price_diff'] * item['count']
                              for item in [r]), 2))
            ))

            if PyMkmHelper.prompt_bool("Do you want to update these prices?") == True:
                # Update articles on MKM
                api.set_stock([r])
                print('Price updated.')
            else:
                print('Prices not updated.')
        else:
            print('No prices to update.')

    @api_wrapper
    def list_competition_for_product(self, api):
        search_string = PyMkmHelper.prompt_string('Search card name')
        is_foil = PyMkmHelper.prompt_bool("Foil?")

        result = api.find_product(search_string, **{
            # 'exact ': 'true',
            'idGame': 1,
            'idLanguage': 1,
            # TODO: Add Partial Content support
            # TODO: Add language support
        })

        if (result):
            products = result['product']

            stock_list_products = [x['idProduct']
                                   for x in self.get_stock_as_array(api=self.api)]
            products = [x for x in products if x['idProduct']
                        in stock_list_products]

            if len(products) == 0:
                print('No matching cards in stock.')
            else:
                if len(products) > 1:
                    product = self.select_from_list_of_products(
                        [i for i in products if i['categoryName'] == 'Magic Single'])
                elif len(products) == 1:
                    product = products[0]

                self.show_competition_for_product(
                    product['idProduct'], product['enName'], is_foil, api=self.api)
        else:
            print('No results found.')

    @api_wrapper
    def show_top_expensive_articles_in_stock(self, num_articles, api):
        stock_list = self.get_stock_as_array(api=self.api)
        table_data = []
        total_price = 0

        for article in stock_list:
            name = article['product']['enName']
            expansion = article.get('product').get('expansion')
            foil = article.get('isFoil')
            language_code = article.get('language')
            language_name = language_code.get('languageName')
            price = article.get('price')
            table_data.append(
                [name, expansion, u'\u2713' if foil else '', language_name if language_code != 1 else '', price])
            total_price += price
        if len(stock_list) > 0:
            print('Top {} most expensive articles in stock:\n'.format(
                str(num_articles)))
            print(tb.tabulate(sorted(table_data, key=lambda x: x[4], reverse=True)[:num_articles],
                              headers=['Name', 'Expansion',
                                       'Foil?', 'Language', 'Price'],
                              tablefmt="simple")
                  )
            print('\nTotal stock value: {}'.format(str(total_price)))
        return None

    @api_wrapper
    def show_account_info(self, api):
        pp = pprint.PrettyPrinter()
        pp.pprint(api.get_account())

    @api_wrapper
    def clear_entire_stock(self, api):
        stock_list = self.get_stock_as_array(api=self.api)
        if PyMkmHelper.prompt_bool("Do you REALLY want to clear your entire stock ({} items)?".format(len(stock_list))) == True:

            # for article in stock_list:
                # article['count'] = 0
            delete_list = [{'count': x['count'], 'idArticle': x['idArticle']}
                           for x in stock_list]

            api.delete_stock(delete_list)
            print('Stock cleared.')
        else:
            print('Aborted.')

    @api_wrapper
    def import_from_csv(self, api):
        print("Note the required format: Card, Set name, Quantity, Foil, Language (with header row).")
        print("Cards are added in condition NM.")
        problem_cards = []
        with open('list.csv', newline='') as csvfile:
            csv_reader = csvfile.readlines()
            index = 0
            bar = progressbar.ProgressBar(
                max_value=(sum(1 for row in csv_reader)) - 1)
            csvfile.seek(0)
            for row in csv_reader:
                if index > 0:
                    (name, set_name, count, foil, language, *other) = row.split(',')
                    if (all(v is not '' for v in [name, set_name, count])):
                        possible_products = api.find_product(name)['product']
                        product_match = [x for x in possible_products if x['expansionName']
                                         == set_name and x['categoryName'] == "Magic Single"]
                        if len(product_match) == 0:
                            problem_cards.append(row)
                        elif len(product_match) == 1:
                            foil = (True if foil == 'Foil' else False)
                            language_id = (
                                1 if language == '' else api.languages.index(language) + 1)
                            price = self.get_price_for_product(
                                product_match[0]['idProduct'], foil, language_id=language_id, api=self.api)
                            card = {
                                'idProduct': product_match[0]['idProduct'],
                                'idLanguage': language_id,
                                'count': count,
                                'price': str(price),
                                'condition': 'NM',
                                'isFoil': ('true' if foil else 'false')
                            }
                            api.add_stock([card])
                        else:
                            problem_cards.append(row)

                bar.update(index)
                index += 1
            bar.finish()
        if len(problem_cards) > 0:
            try:
                with open('failed_imports.csv', 'w', newline='', encoding='utf-8') as csvfile:
                    csv_writer = csv.writer(csvfile)
                    csv_writer.writerows(problem_cards)
                print('Wrote failed imports to failed_imports.csv')
                print(
                    'Most failures are due to mismatching set names or multiple versions of cards.')
            except Exception as err:
                print(err.value)

# End of menu item functions ============================================

    def select_from_list_of_products(self, products):
        index = 1
        for product in products:
            print('{}: {} [{}] {}'.format(index, product['enName'],
                                          product['expansionName'], product['rarity']))
            index += 1
        choice = int(input("Choose card: "))
        return products[choice - 1]

    def select_from_list_of_articles(self, articles):
        index = 1
        for article in articles:
            product = article['product']
            print('{}: {} [{}] {}'.format(index, product['enName'],
                                          product['expansion'], product['rarity']))
            index += 1
        choice = int(input("Choose card: "))
        return articles[choice - 1]

    def show_competition_for_product(self, product_id, product_name, is_foil, api):
        print("Found product: {}".format(product_name))
        account = api.get_account()['account']
        country_code = account['country']
        articles = api.get_articles(product_id, **{
            'isFoil': str(is_foil).lower(),
            'isAltered': 'false',
            'isSigned': 'false',
            'minCondition': 'EX',
            'country': country_code,
            'idLanguage': 1
        })
        table_data = []
        table_data_local = []
        for article in articles:
            username = article['seller']['username']
            if article['seller']['username'] == account['username']:
                username = '-> ' + username
            item = [
                username,
                article['seller']['address']['country'],
                article['condition'],
                article['count'],
                article['price']
            ]
            if article['seller']['address']['country'] == country_code:
                table_data_local.append(item)
            table_data.append(item)
        if table_data_local:
            self.print_product_top_list(
                "Local competition:", table_data_local, 4, 20)
        if table_data:
            self.print_product_top_list("Top 20 cheapest:", table_data, 4, 20)
        else:
            print('No prices found.')

    def print_product_top_list(self, title_string, table_data, sort_column, rows):
        print(70*'-')
        print('{} \n'.format(title_string))
        print(tb.tabulate(sorted(table_data, key=lambda x: x[sort_column], reverse=False)[:rows],
                          headers=['Username', 'Country',
                                   'Condition', 'Count', 'Price'],
                          tablefmt="simple"))
        print(70*'-')
        print('Total average price: {}, Total median price: {}, Total # of articles: {}\n'.format(
            str(PyMkmHelper.calculate_average(table_data, 3, 4)),
            str(PyMkmHelper.calculate_median(table_data, 3, 4)),
            str(len(table_data))
        )
        )

    def calculate_new_prices_for_stock(self, api):
        stock_list = self.get_stock_as_array(api=self.api)
        # HACK: filter out a foil product
        # stock_list = [x for x in stock_list if x['isFoil']]

        result_json = []
        total_price = 0
        index = 0

        bar = progressbar.ProgressBar(max_value=len(stock_list))
        for article in stock_list:
            updated_article = self.get_price_for_single_article(
                article, api=self.api)
            if updated_article:
                result_json.append(updated_article)
                total_price += updated_article.get('price')
            else:
                total_price += article.get('price')
            index += 1
            bar.update(index)
        bar.finish()

        print('Total stock value: {}'.format(str(total_price)))
        return result_json

    def get_price_for_single_article(self, article, api):
        # TODO: compare prices also for signed cards, like foils
        if not article.get('isSigned') or True:  # keep prices for signed cards fixed
            new_price = self.get_price_for_product(
                article['idProduct'], 
                article['product']['rarity'], 
                article['isFoil'], 
                language_id=article['language']['idLanguage'],
                api=self.api)
            price_diff = new_price - article['price']
            if price_diff != 0:
                return {
                    "name": article['product']['enName'],
                    "foil": article['isFoil'],
                    "old_price": article['price'],
                    "price": new_price,
                    "price_diff": price_diff,
                    "idArticle": article['idArticle'],
                    "count": article['count']
                }

    def get_rounding_limit_for_rarity(self, rarity):
        rounding_limit = self.config['price_limit_by_rarity']['default']
        try:
            rounding_limit = float(
                self.config['price_limit_by_rarity'][rarity.lower()])
        except KeyError as err:
            print(f"ERROR: Unknown rarity '{rarity}'. Using default rounding.")
        return rounding_limit

    def get_price_for_product(self, product_id, rarity, is_foil, language_id=1, api=None):
        if not is_foil:
            r = api.get_product(product_id)
            rounding_limit = self.get_rounding_limit_for_rarity(rarity)
            new_price_rounded = PyMkmHelper.round_up_to_limit(
                rounding_limit,
                r['product']['priceGuide']['TREND'])
        else:
            new_price_rounded = self.get_foil_price(
                api, product_id, rarity, language_id)

        if new_price_rounded == None:
            raise ValueError('No price found!')
        else:
            return new_price_rounded

    def get_foil_price(self, api, product_id, rarity, language_id):
        # NOTE: This is a rough algorithm, designed to be safe and not to sell aggressively.
        # 1) See filter parameters below.
        # 2) Set price to lowest + (median - lowest / 4), rounded to closest § Euro.
        # 3) Undercut price in own country if not contradicting 2)
        # 4) Never go below 0.25 for foils

        rounding_limit = self.get_rounding_limit_for_rarity(rarity)

        account = api.get_account()['account']
        articles = api.get_articles(product_id, **{
            'isFoil': 'true',
            'isAltered': 'false',
            'isSigned': 'false',
            'minCondition': 'GD',
            'idLanguage': language_id
        })

        keys = ['idArticle', 'count', 'price', 'condition', 'seller']
        foil_articles = [{x: y for x, y in art.items() if x in keys}
                         for art in articles]
        local_articles = []
        for article in foil_articles:
            if article['seller']['address']['country'] == account['country'] and article['seller']['username'] != account['username']:
                local_articles.append(article)

        local_table_data = []
        for article in local_articles:
            if article:
                local_table_data.append([
                    article['seller']['username'],
                    article['seller']['address']['country'],
                    article['condition'],
                    article['count'],
                    article['price']
                ])

        table_data = []
        for article in foil_articles:
            if article:
                table_data.append([
                    article['seller']['username'],
                    article['seller']['address']['country'],
                    article['condition'],
                    article['count'],
                    article['price']
                ])

        median_price = PyMkmHelper.calculate_median(table_data, 3, 4)
        lowest_price = PyMkmHelper.calculate_lowest(table_data, 4)
        median_guided = PyMkmHelper.round_up_to_limit(rounding_limit,
                                                      lowest_price + (median_price - lowest_price) / 4)

        if len(local_table_data) > 0:
            # Undercut if there is local competition
            lowest_in_country = PyMkmHelper.round_down_to_limit(rounding_limit,
                                                                PyMkmHelper.calculate_lowest(local_table_data, 4))
            return max(rounding_limit, min(median_guided, lowest_in_country - rounding_limit))
        else:
            # No competition in our country, set price a bit higher.
            return PyMkmHelper.round_up_to_limit(rounding_limit, median_guided * 1.2)

    def display_price_changes_table(self, changes_json):
        # table breaks because of progress bar rendering
        print('\nBest diffs:\n')
        sorted_best = sorted(
            changes_json, key=lambda x: x['price_diff'], reverse=True)[:10]
        self.draw_price_changes_table(
            i for i in sorted_best if i['price_diff'] > 0)
        print('\nWorst diffs:\n')
        sorted_worst = sorted(changes_json, key=lambda x: x['price_diff'])[:10]
        self.draw_price_changes_table(
            i for i in sorted_worst if i['price_diff'] < 0)

        print('\nTotal price difference: {}.'.format(
            str(round(sum(item['price_diff'] * item['count']
                          for item in sorted_best), 2))
        ))

    def draw_price_changes_table(self, sorted_best):
        print(tb.tabulate(
            [
                [item['count'],
                 item['name'],
                 u'\u2713' if item['foil'] else '',
                    item['old_price'],
                    item['price'],
                 item['price_diff']] for item in sorted_best],
            headers=['Count', 'Name', 'Foil?',
                     'Old price', 'New price', 'Diff'],
            tablefmt="simple"
        ))

    def get_stock_as_array(self, api):
        d = api.get_stock()

        keys = ['idArticle', 'idProduct', 'product', 'count',
                'price', 'isFoil', 'isSigned', 'language']  # TODO: [language][languageId]
        stock_list = [{x: y for x, y in article.items() if x in keys}
                      for article in d]
        return stock_list
