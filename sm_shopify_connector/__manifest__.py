# -*- coding: utf-8 -*-
{
    'name': 'Shopify Connector',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Connect Shopify with Odoo, import products, customers, orders, and monitor sync logs from a dashboard',
    'description': """
Shopify Connector
=====================
Connect Shopify stores with Odoo using Shopify GraphQL Admin API and Shopify client credentials.

Main Features
-------------
* Configure multiple Shopify stores with company, warehouse, pricelist, and API version.
* Fetch Shopify access token from Client ID and Client Secret.
* Test Shopify connection directly from Odoo.
* Import Shopify products and variants into Odoo products.
* Import product price, SKU, barcode, image, vendor, type, tags, handle, and Shopify status.
* Import Shopify customers into Odoo contacts with email, phone, and address data.
* Import Shopify orders into Odoo quotations or confirmed sales orders.
* Map Shopify financial status and fulfillment status on sales orders.
* Match products by Shopify variant ID or SKU during order import.
* Create missing products from Shopify order lines when needed.
* Configure import limits for products, customers, and orders.
* Track last product, customer, and order import date on each store.
* Review imported product, customer, order, and log counts with smart buttons.
* Record sync logs for connection, product import, customer import, order import, and full sync.
* Monitor stores, connected status, imported records, failed logs, recent activity, and sync history from the Shopify dashboard.
* Filter dashboard data by date range, store, operation, and status.
    """,
    'author': 'Steven Marp',
    'website': 'https://apps.odoo.com/apps/modules/browse?repo_maintainer_id=512936',
    'license': 'OPL-1',
    'depends': ['sale_management', 'sale_stock'],
    'data': [
        'security/shopify_security.xml',
        'security/ir.model.access.csv',
        'views/shopify_sync_log_views.xml',
        'views/shopify_instance_views.xml',
        'views/product_views.xml',
        'views/partner_views.xml',
        'views/sale_order_views.xml',
        'views/shopify_dashboard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sm_shopify_connector/static/src/scss/shopify_dashboard.scss',
            'sm_shopify_connector/static/src/js/shopify_dashboard.js',
            'sm_shopify_connector/static/src/xml/shopify_dashboard.xml',
        ],
    },
    'images': [
        'static/description/banner.gif',
        'static/description/icon.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 79.00,
    'currency': 'USD',
}
