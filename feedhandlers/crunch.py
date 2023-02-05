from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # For embeds only
    # https://s.crunch.io/widget/index.html#/ds/ee9e2f63077049b6ac09cac6e84f17f3/row/0zbIusKY9C0GjpLpSB5WfW000735?viz=horizontalBarPlot&cp=percent&dp=0&grp=stack
    item = {}
    ss_url = '{}/screenshot?url={}&locator=crosstab&width=800&height=800'.format(config.server, quote_plus(url))
    caption = '<a href="{}">View chart</a>'
    item['content_html'] = utils.add_image(ss_url, caption, link=url)
    return item
