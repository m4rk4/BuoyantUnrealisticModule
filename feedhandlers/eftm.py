from feedhandlers import rss, wp_posts


def get_content(url, args, save_debug=False):
    item = wp_posts.get_content(url, args, save_debug)
    # TODO: this is stupid
    item['content_html'] = item['content_html'].replace('src="https://cdn.eftm.com/wp-content/uploads/', 'src="http://cdn.eftm.com/wp-content/uploads/')
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
