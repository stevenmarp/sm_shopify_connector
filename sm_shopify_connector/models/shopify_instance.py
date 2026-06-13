# -*- coding: utf-8 -*-
import base64
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ShopifyGraphQLClient:
    def __init__(self, shop_url, access_token, api_version):
        clean_url = (shop_url or '').replace('https://', '').replace('http://', '').rstrip('/')
        self.endpoint = 'https://%s/admin/api/%s/graphql.json' % (clean_url, api_version)
        self.headers = {
            'Content-Type': 'application/json',
            'X-Shopify-Access-Token': access_token or '',
        }

    def execute(self, query, variables=None):
        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json={'query': query, 'variables': variables or {}},
                timeout=40,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.HTTPError as error:
            body = error.response.text if error.response is not None else str(error)
            raise UserError(_('Shopify API error: %s') % body) from error
        except requests.exceptions.RequestException as error:
            raise UserError(_('Could not connect to Shopify: %s') % error) from error

        if payload.get('errors'):
            raise UserError(_('Shopify GraphQL error: %s') % payload['errors'])
        return payload.get('data') or {}


class ShopifyInstance(models.Model):
    _name = 'shopify.instance'
    _description = 'Shopify Store'
    _order = 'name'

    name = fields.Char(required=True)
    shop_url = fields.Char(required=True, help='Example: your-store.myshopify.com')
    auth_method = fields.Selection([
        ('client_credentials', 'Client Credentials'),
        ('access_token', 'Access Token'),
    ], default='client_credentials', required=True)
    client_id = fields.Char()
    client_secret = fields.Char()
    access_token = fields.Char()
    token_expires_at = fields.Datetime(readonly=True)
    token_scope = fields.Char(readonly=True)
    api_version = fields.Selection([
        ('2025-07', '2025-07'),
        ('2025-10', '2025-10'),
        ('2026-01', '2026-01'),
        ('2026-04', '2026-04'),
    ], default='2026-04', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], default='draft', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True, default=lambda self: self._default_warehouse())
    pricelist_id = fields.Many2one('product.pricelist')
    import_order_state = fields.Selection([
        ('draft', 'Import as Quotation'),
        ('sale', 'Import and Confirm'),
    ], default='draft', required=True)
    product_limit = fields.Integer(default=50)
    customer_limit = fields.Integer(default=50)
    order_limit = fields.Integer(default=50)
    last_product_import = fields.Datetime(readonly=True)
    last_customer_import = fields.Datetime(readonly=True)
    last_order_import = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)
    product_count = fields.Integer(compute='_compute_counts')
    customer_count = fields.Integer(compute='_compute_counts')
    order_count = fields.Integer(compute='_compute_counts')
    sync_log_count = fields.Integer(compute='_compute_counts')

    @api.model
    def _default_warehouse(self):
        return self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)

    def _compute_counts(self):
        Product = self.env['product.product']
        Partner = self.env['res.partner']
        Order = self.env['sale.order']
        Log = self.env['shopify.sync.log']
        for instance in self:
            instance.product_count = Product.search_count([('shopify_instance_id', '=', instance.id)])
            instance.customer_count = Partner.search_count([('shopify_instance_id', '=', instance.id)])
            instance.order_count = Order.search_count([('shopify_instance_id', '=', instance.id)])
            instance.sync_log_count = Log.search_count([('instance_id', '=', instance.id)])

    def _client(self):
        self.ensure_one()
        return ShopifyGraphQLClient(self.shop_url, self._get_access_token(), self.api_version)

    def _shop_domain(self):
        self.ensure_one()
        return (self.shop_url or '').replace('https://', '').replace('http://', '').rstrip('/')

    def _get_access_token(self):
        self.ensure_one()
        if self.auth_method == 'access_token':
            if not self.access_token:
                raise UserError(_('Access token is required.'))
            return self.access_token
        if not self.access_token or not self.token_expires_at or self.token_expires_at <= fields.Datetime.now() + timedelta(minutes=5):
            self._refresh_access_token()
        return self.access_token

    def action_refresh_access_token(self):
        self.ensure_one()
        self._refresh_access_token()
        self.env['shopify.sync.log'].sm_log(self, 'connection', 'success', 1, _('Access token refreshed.'))
        return self._notify(_('Shopify Token Ready'), _('Access token generated from Client ID and Secret.'), 'success')

    def _refresh_access_token(self):
        self.ensure_one()
        if not self.client_id or not self.client_secret:
            raise UserError(_('Client ID and Client Secret are required.'))
        endpoint = 'https://%s/admin/oauth/access_token' % self._shop_domain()
        try:
            response = requests.post(
                endpoint,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'client_credentials',
                },
                timeout=40,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.HTTPError as error:
            body = error.response.text if error.response is not None else str(error)
            if 'app_not_installed' in body:
                body = _('The Shopify app is not installed on this store. Install the released app from Dev Dashboard, then fetch token again.')
            elif 'shop_not_permitted' in body:
                body = _('This store is not permitted for client credentials. Use a store owned by the same organization, or use OAuth authorization code flow.')
            raise UserError(_('Shopify token error: %s') % body) from error
        except requests.exceptions.RequestException as error:
            raise UserError(_('Could not request Shopify token: %s') % error) from error

        token = payload.get('access_token')
        if not token:
            raise UserError(_('Shopify did not return an access token.'))
        expires_in = int(payload.get('expires_in') or 86400)
        self.write({
            'access_token': token,
            'token_scope': payload.get('scope') or False,
            'token_expires_at': fields.Datetime.now() + timedelta(seconds=max(expires_in - 300, 60)),
        })
        return token

    def action_test_connection(self):
        self.ensure_one()
        query = '''
            query {
                shop {
                    name
                    myshopifyDomain
                    currencyCode
                }
            }
        '''
        data = self._client().execute(query)
        shop = data.get('shop') or {}
        if not shop:
            self.state = 'error'
            raise UserError(_('Connection failed. Shopify did not return shop data.'))
        self.write({'state': 'connected', 'name': shop.get('name') or self.name})
        self.env['shopify.sync.log'].sm_log(self, 'connection', 'success', 1, _('Connected to %s') % shop.get('myshopifyDomain'))
        return self._notify(_('Shopify Connected'), _('Connected to %s') % shop.get('myshopifyDomain'), 'success')

    def action_import_products(self):
        self.ensure_one()
        count = 0
        try:
            for node in self._shopify_products():
                count += self._import_shopify_product(node)
            self.write({'last_product_import': fields.Datetime.now()})
            self.env['shopify.sync.log'].sm_log(self, 'product', 'success', count, _('Products imported.'))
            return self._notify(_('Products Imported'), _('%s products imported or updated.') % count, 'success')
        except Exception as error:
            self.env['shopify.sync.log'].sm_log(self, 'product', 'failed', count, str(error))
            raise

    def action_import_customers(self):
        self.ensure_one()
        count = 0
        try:
            for node in self._shopify_customers():
                self._import_shopify_customer(node)
                count += 1
            self.write({'last_customer_import': fields.Datetime.now()})
            self.env['shopify.sync.log'].sm_log(self, 'customer', 'success', count, _('Customers imported.'))
            return self._notify(_('Customers Imported'), _('%s customers imported or updated.') % count, 'success')
        except Exception as error:
            self.env['shopify.sync.log'].sm_log(self, 'customer', 'failed', count, str(error))
            raise

    def action_import_orders(self):
        self.ensure_one()
        count = 0
        try:
            for node in self._shopify_orders():
                self._import_shopify_order(node)
                count += 1
            self.write({'last_order_import': fields.Datetime.now()})
            self.env['shopify.sync.log'].sm_log(self, 'order', 'success', count, _('Orders imported.'))
            return self._notify(_('Orders Imported'), _('%s orders imported or updated.') % count, 'success')
        except Exception as error:
            self.env['shopify.sync.log'].sm_log(self, 'order', 'failed', count, str(error))
            raise

    def action_import_all(self):
        self.ensure_one()
        self.action_import_products()
        self.action_import_customers()
        self.action_import_orders()
        self.env['shopify.sync.log'].sm_log(self, 'all', 'success', 0, _('Full sync finished.'))
        return self._notify(_('Shopify Sync Finished'), _('Products, customers, and orders imported.'), 'success')

    def action_view_products(self):
        self.ensure_one()
        return self._action_records(_('Shopify Products'), 'product.product', [('shopify_instance_id', '=', self.id)], 'list,form')

    def action_view_customers(self):
        self.ensure_one()
        return self._action_records(_('Shopify Customers'), 'res.partner', [('shopify_instance_id', '=', self.id)], 'list,form')

    def action_view_orders(self):
        self.ensure_one()
        return self._action_records(_('Shopify Orders'), 'sale.order', [('shopify_instance_id', '=', self.id)], 'list,form')

    def action_view_logs(self):
        self.ensure_one()
        return self._action_records(_('Shopify Sync Logs'), 'shopify.sync.log', [('instance_id', '=', self.id)], 'list,form')

    def _action_records(self, name, model, domain, view_mode):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': view_mode,
            'domain': domain,
            'target': 'current',
        }

    def _shopify_products(self):
        query = '''
            query($first: Int!, $after: String) {
                products(first: $first, after: $after, sortKey: UPDATED_AT, reverse: true) {
                    edges {
                        cursor
                        node {
                            id title handle status vendor productType tags descriptionHtml
                            featuredImage { url }
                            variants(first: 100) {
                                edges {
                                    node {
                                        id title sku barcode price
                                        image { url }
                                        inventoryItem { id tracked }
                                    }
                                }
                            }
                        }
                    }
                    pageInfo { hasNextPage endCursor }
                }
            }
        '''
        return self._paginate(query, 'products', self.product_limit)

    def _shopify_customers(self):
        query = '''
            query($first: Int!, $after: String) {
                customers(first: $first, after: $after, sortKey: UPDATED_AT, reverse: true) {
                    edges {
                        cursor
                        node {
                            id firstName lastName email phone
                            defaultAddress { address1 address2 city zip phone countryCodeV2 provinceCode }
                        }
                    }
                    pageInfo { hasNextPage endCursor }
                }
            }
        '''
        return self._paginate(query, 'customers', self.customer_limit)

    def _shopify_orders(self):
        query = '''
            query($first: Int!, $after: String) {
                orders(first: $first, after: $after, sortKey: CREATED_AT, reverse: true) {
                    edges {
                        cursor
                        node {
                            id name email phone createdAt displayFinancialStatus displayFulfillmentStatus
                            customer { id firstName lastName email phone defaultAddress { address1 address2 city zip phone countryCodeV2 provinceCode } }
                            shippingAddress { name address1 address2 city zip phone countryCodeV2 provinceCode }
                            lineItems(first: 100) {
                                edges {
                                    node {
                                        title quantity sku
                                        variant { id sku product { id } }
                                        originalUnitPriceSet { shopMoney { amount currencyCode } }
                                        discountedTotalSet { shopMoney { amount currencyCode } }
                                    }
                                }
                            }
                        }
                    }
                    pageInfo { hasNextPage endCursor }
                }
            }
        '''
        return self._paginate(query, 'orders', self.order_limit)

    def _paginate(self, query, root_key, limit):
        client = self._client()
        remaining = max(limit or 1, 1)
        after = None
        while remaining > 0:
            batch = min(remaining, 50)
            data = client.execute(query, {'first': batch, 'after': after})
            root = data.get(root_key) or {}
            edges = root.get('edges') or []
            for edge in edges:
                remaining -= 1
                yield edge.get('node') or {}
            page_info = root.get('pageInfo') or {}
            if not page_info.get('hasNextPage') or not edges or remaining <= 0:
                break
            after = page_info.get('endCursor')

    def _import_shopify_product(self, node):
        variants = ((node.get('variants') or {}).get('edges') or [])
        if not variants:
            variants = [{'node': {'id': node.get('id'), 'title': 'Default Title', 'sku': False, 'price': 0.0}}]
        count = 0
        for edge in variants:
            variant = edge.get('node') or {}
            product = self._upsert_variant_product(node, variant)
            image_url = ((variant.get('image') or {}).get('url') or (node.get('featuredImage') or {}).get('url'))
            if image_url and not product.image_1920:
                self._set_product_image(product.product_tmpl_id, image_url)
            count += 1
        return count

    def _upsert_variant_product(self, product_data, variant_data):
        Product = self.env['product.product']
        variant_gid = variant_data.get('id') or product_data.get('id')
        product = Product.search([
            ('shopify_instance_id', '=', self.id),
            ('shopify_variant_gid', '=', variant_gid),
        ], limit=1)
        variant_title = variant_data.get('title') or ''
        name = product_data.get('title') or _('Shopify Product')
        if variant_title and variant_title != 'Default Title':
            name = '%s - %s' % (name, variant_title)
        sku = variant_data.get('sku') or False
        price = self._to_float(variant_data.get('price'))
        template_vals = {
            'name': name,
            'sale_ok': True,
            'purchase_ok': False,
            'type': 'consu',
            'list_price': price,
            'default_code': sku,
            'barcode': variant_data.get('barcode') or False,
            'description_sale': product_data.get('descriptionHtml') or False,
            'shopify_instance_id': self.id,
            'shopify_product_gid': product_data.get('id'),
            'shopify_handle': product_data.get('handle'),
            'shopify_status': product_data.get('status'),
            'shopify_vendor': product_data.get('vendor'),
            'shopify_product_type': product_data.get('productType'),
            'shopify_tags': ', '.join(product_data.get('tags') or []),
            'shopify_last_imported': fields.Datetime.now(),
        }
        variant_vals = {
            'shopify_instance_id': self.id,
            'shopify_product_gid': product_data.get('id'),
            'shopify_variant_gid': variant_gid,
            'shopify_inventory_item_gid': (variant_data.get('inventoryItem') or {}).get('id'),
            'shopify_last_imported': fields.Datetime.now(),
        }
        if product:
            product.product_tmpl_id.write(template_vals)
            product.write(variant_vals)
            return product
        template = self.env['product.template'].create(template_vals)
        template.product_variant_id.write(variant_vals)
        return template.product_variant_id

    def _set_product_image(self, template, image_url):
        try:
            response = requests.get(image_url, timeout=20)
            response.raise_for_status()
            template.image_1920 = base64.b64encode(response.content)
        except Exception as error:
            _logger.info('Could not import Shopify image %s: %s', image_url, error)

    def _import_shopify_customer(self, node):
        Partner = self.env['res.partner']
        partner = Partner.search([
            ('shopify_instance_id', '=', self.id),
            ('shopify_customer_gid', '=', node.get('id')),
        ], limit=1)
        if not partner and node.get('email'):
            partner = Partner.search([('email', '=', node.get('email'))], limit=1)
        vals = self._partner_vals_from_customer(node)
        if partner:
            partner.write(vals)
        else:
            partner = Partner.create(vals)
        return partner

    def _partner_vals_from_customer(self, node):
        address = node.get('defaultAddress') or {}
        name = ('%s %s' % (node.get('firstName') or '', node.get('lastName') or '')).strip()
        return {
            'name': name or node.get('email') or _('Shopify Customer'),
            'email': node.get('email') or False,
            'phone': node.get('phone') or address.get('phone') or False,
            'street': address.get('address1') or False,
            'street2': address.get('address2') or False,
            'city': address.get('city') or False,
            'zip': address.get('zip') or False,
            'country_id': self._country_id(address.get('countryCodeV2')),
            'state_id': self._state_id(address.get('countryCodeV2'), address.get('provinceCode')),
            'shopify_instance_id': self.id,
            'shopify_customer_gid': node.get('id'),
            'shopify_last_imported': fields.Datetime.now(),
        }

    def _import_shopify_order(self, node):
        Order = self.env['sale.order']
        order = Order.search([
            ('shopify_instance_id', '=', self.id),
            ('shopify_order_gid', '=', node.get('id')),
        ], limit=1)
        if order and order.state != 'draft':
            order.write(self._sale_order_status_vals(node))
            return order
        partner = self._partner_from_order(node)
        vals = {
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'warehouse_id': self.warehouse_id.id,
            'origin': node.get('name'),
            'client_order_ref': node.get('name'),
            'shopify_instance_id': self.id,
            'shopify_order_gid': node.get('id'),
            'shopify_order_name': node.get('name'),
            'shopify_last_imported': fields.Datetime.now(),
            **self._sale_order_status_vals(node),
        }
        if self.pricelist_id:
            vals['pricelist_id'] = self.pricelist_id.id
        if order:
            order.order_line.unlink()
            order.write(vals)
        else:
            order = Order.create(vals)
        for edge in ((node.get('lineItems') or {}).get('edges') or []):
            self._create_order_line(order, edge.get('node') or {})
        if self.import_order_state == 'sale' and order.state == 'draft':
            order.action_confirm()
        return order

    def _sale_order_status_vals(self, node):
        return {
            'shopify_financial_status': node.get('displayFinancialStatus') or False,
            'shopify_fulfillment_status': node.get('displayFulfillmentStatus') or False,
        }

    def _partner_from_order(self, node):
        customer = node.get('customer') or {}
        if customer.get('id'):
            return self._import_shopify_customer(customer)
        email = node.get('email')
        partner = self.env['res.partner'].search([('email', '=', email)], limit=1) if email else False
        if partner:
            return partner
        shipping = node.get('shippingAddress') or {}
        return self.env['res.partner'].create({
            'name': shipping.get('name') or email or node.get('name') or _('Shopify Customer'),
            'email': email or False,
            'phone': node.get('phone') or shipping.get('phone') or False,
            'street': shipping.get('address1') or False,
            'street2': shipping.get('address2') or False,
            'city': shipping.get('city') or False,
            'zip': shipping.get('zip') or False,
            'country_id': self._country_id(shipping.get('countryCodeV2')),
            'state_id': self._state_id(shipping.get('countryCodeV2'), shipping.get('provinceCode')),
            'shopify_instance_id': self.id,
            'shopify_last_imported': fields.Datetime.now(),
        })

    def _create_order_line(self, order, line):
        product = self._find_line_product(line)
        quantity = line.get('quantity') or 1
        price = self._line_unit_price(line, quantity)
        return self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': product.id,
            'name': line.get('title') or product.display_name,
            'product_uom_qty': quantity,
            'price_unit': price,
        })

    def _find_line_product(self, line):
        Product = self.env['product.product']
        variant = line.get('variant') or {}
        product = False
        if variant.get('id'):
            product = Product.search([
                ('shopify_instance_id', '=', self.id),
                ('shopify_variant_gid', '=', variant.get('id')),
            ], limit=1)
        sku = line.get('sku') or variant.get('sku')
        if not product and sku:
            product = Product.search([('default_code', '=', sku)], limit=1)
        if product:
            return product
        template = self.env['product.template'].create({
            'name': line.get('title') or _('Shopify Product'),
            'sale_ok': True,
            'purchase_ok': False,
            'type': 'consu',
            'default_code': sku or False,
            'list_price': self._line_unit_price(line, line.get('quantity') or 1),
            'shopify_instance_id': self.id,
            'shopify_product_gid': (variant.get('product') or {}).get('id'),
            'shopify_last_imported': fields.Datetime.now(),
        })
        template.product_variant_id.write({
            'shopify_instance_id': self.id,
            'shopify_product_gid': (variant.get('product') or {}).get('id'),
            'shopify_variant_gid': variant.get('id'),
            'shopify_last_imported': fields.Datetime.now(),
        })
        return template.product_variant_id

    def _line_unit_price(self, line, quantity):
        total = (((line.get('discountedTotalSet') or {}).get('shopMoney') or {}).get('amount'))
        if total is not None and quantity:
            total_value = self._to_decimal(total)
            if total_value is not False:
                return float(total_value / Decimal(str(quantity)))
        amount = (((line.get('originalUnitPriceSet') or {}).get('shopMoney') or {}).get('amount'))
        return self._to_float(amount)

    def _country_id(self, code):
        if not code:
            return False
        country = self.env['res.country'].search([('code', '=', code)], limit=1)
        return country.id or False

    def _state_id(self, country_code, state_code):
        if not country_code or not state_code:
            return False
        state = self.env['res.country.state'].search([
            ('code', '=', state_code),
            ('country_id.code', '=', country_code),
        ], limit=1)
        return state.id or False

    def _to_decimal(self, value):
        try:
            return Decimal(str(value or '0'))
        except (InvalidOperation, ValueError):
            return False

    def _to_float(self, value):
        decimal_value = self._to_decimal(value)
        return float(decimal_value) if decimal_value is not False else 0.0

    def _notify(self, title, message, notif_type='info', reload=False):
        action = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notif_type,
                'sticky': False,
            },
        }
        if reload:
            action['params']['next'] = {'type': 'ir.actions.client', 'tag': 'reload'}
        return action

    @api.model
    def sm_shopify_dashboard_filters(self):
        return {
            'instances': self.search_read([], ['id', 'name'], order='name'),
            'operations': [{'code': key, 'name': value} for key, value in self.env['shopify.sync.log']._fields['operation'].selection],
            'states': [{'code': key, 'name': value} for key, value in self.env['shopify.sync.log']._fields['state'].selection],
        }

    @api.model
    def sm_shopify_dashboard_data(self, filters=None):
        filters = filters or {}
        date_to = self._sm_dashboard_to_date(filters.get('date_to')) or fields.Date.context_today(self)
        date_from = self._sm_dashboard_to_date(filters.get('date_from')) or (date_to - timedelta(days=29))
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        instance_ids = [int(value) for value in filters.get('instance_ids', []) if value]
        operations = filters.get('operations') or [item[0] for item in self.env['shopify.sync.log']._fields['operation'].selection]
        states = filters.get('states') or [item[0] for item in self.env['shopify.sync.log']._fields['state'].selection]

        instances = self.search([('id', 'in', instance_ids)] if instance_ids else [])
        log_domain = self._sm_dashboard_log_domain(date_from, date_to, instance_ids, operations, states)
        logs = self.env['shopify.sync.log'].search(log_domain, order='create_date desc, id desc')

        return {
            'summary': self._sm_dashboard_summary(instances, logs),
            'cards': self._sm_dashboard_cards(instances),
            'recent': self._sm_dashboard_recent_logs(logs[:20]),
            'activity': self._sm_dashboard_activity(logs, date_from, date_to),
        }

    @api.model
    def _sm_dashboard_to_date(self, value):
        if not value:
            return False
        return fields.Date.from_string(value) if isinstance(value, str) else value

    def _sm_dashboard_log_domain(self, date_from, date_to, instance_ids, operations, states):
        date_to_dt = fields.Datetime.to_datetime(date_to) + timedelta(hours=23, minutes=59, seconds=59)
        domain = [
            ('create_date', '>=', fields.Datetime.to_datetime(date_from)),
            ('create_date', '<=', date_to_dt),
            ('operation', 'in', operations),
            ('state', 'in', states),
        ]
        if instance_ids:
            domain.append(('instance_id', 'in', instance_ids))
        return domain

    def _sm_dashboard_summary(self, instances, logs):
        return {
            'stores': len(instances),
            'connected': len(instances.filtered(lambda item: item.state == 'connected')),
            'products': sum(instances.mapped('product_count')),
            'customers': sum(instances.mapped('customer_count')),
            'orders': sum(instances.mapped('order_count')),
            'success': len(logs.filtered(lambda item: item.state == 'success')),
            'failed': len(logs.filtered(lambda item: item.state == 'failed')),
            'total_logs': len(logs),
        }

    def _sm_dashboard_cards(self, instances):
        result = []
        for instance in instances:
            result.append({
                'id': instance.id,
                'name': instance.name,
                'shop_url': instance.shop_url,
                'state': instance.state,
                'state_label': dict(instance._fields['state'].selection).get(instance.state, instance.state),
                'products': instance.product_count,
                'customers': instance.customer_count,
                'orders': instance.order_count,
                'logs': instance.sync_log_count,
                'last_product_import': fields.Datetime.to_string(instance.last_product_import) if instance.last_product_import else '-',
                'last_customer_import': fields.Datetime.to_string(instance.last_customer_import) if instance.last_customer_import else '-',
                'last_order_import': fields.Datetime.to_string(instance.last_order_import) if instance.last_order_import else '-',
            })
        return result

    def _sm_dashboard_recent_logs(self, logs):
        operation_labels = dict(logs._fields['operation'].selection)
        state_labels = dict(logs._fields['state'].selection)
        return [{
            'id': log.id,
            'date': fields.Datetime.to_string(log.create_date),
            'instance': log.instance_id.name,
            'operation': log.operation,
            'operation_label': operation_labels.get(log.operation, log.operation),
            'state': log.state,
            'state_label': state_labels.get(log.state, log.state),
            'records': log.records_processed,
            'message': log.message or '',
        } for log in logs]

    def _sm_dashboard_activity(self, logs, date_from, date_to):
        labels = []
        total = []
        success = []
        failed = []
        current = date_from
        while current <= date_to:
            day_logs = logs.filtered(lambda log, day=current: log.create_date and fields.Datetime.to_datetime(log.create_date).date() == day)
            labels.append(fields.Date.to_string(current))
            total.append(len(day_logs))
            success.append(len(day_logs.filtered(lambda log: log.state == 'success')))
            failed.append(len(day_logs.filtered(lambda log: log.state == 'failed')))
            current += timedelta(days=1)
        return {
            'labels': labels,
            'total': total,
            'success': success,
            'failed': failed,
            'max': max(total + success + failed + [1]),
        }
