import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(image, width=1000):
    return 'https://images.bauerhosting.com/{}/{}?format=jpg&quality=80&width={}&ratio=16-9&resize=aspectfill'.format(image['path'], image['fileName'], width)


def add_image(content):
    captions = []
    if content.get('caption'):
        captions.append(content['caption'])
    if content.get('credits'):
        captions.append(content['credits'])
    caption = ' | '.join(captions)
    img_src = resize_image(content['image'])
    return utils.add_image(img_src, caption)


def get_latest_articles():
    post_data = {
        "variables":{"categoryGaming": "gaming", "categoryMovies": "movies", "subCategoryFeatures": "features", "subCategoryReviews": "reviews", "categoryTv": "tv", "categoryShopping": "shopping", "maxArticles": 10, "section": "article", "brand": "empire", "hostname":"https://www.empireonline.com"},
        "query": "\n  query getArticles(\n    $brand: String!\n    $categoryMovies: String!\n    $subCategoryReviews: String!\n    $subCategoryFeatures: String!\n    $categoryTv: String!\n    $categoryGaming: String!\n    $categoryShopping: String!\n    $maxArticles: Int!\n    $hostname: String!\n    $section: String!\n  ) {\n    getMetaTemplate(brand: $brand, hostname: $hostname, section: $section) {\n      meta_title\n      meta_description\n    }\n    getContentPinningArticles(brand: $brand) {\n      id\n      title\n      subtitle\n      furl\n      rating\n      hasVideo\n      hasGallery\n      excerpt\n      heroImage {\n        image {\n          fileName\n          path\n          width\n          height\n        }\n        altText\n        description\n        credits\n      }\n      categories {\n        parent {\n          name\n          furl\n        }\n        name\n        furl\n      }\n      publicationDate\n      heroImage {\n        image {\n          fileName\n          path\n          width\n          height\n        }\n        altText\n        description\n        credits\n      }\n      _layout {\n        content {\n          image {\n            fileName\n            path\n            width\n            height\n          }\n        }\n        handles {\n          width\n          height\n          x\n          y\n          x2\n          y2\n          _field\n        }\n        type\n      }\n      urls\n      publications {\n        hostname {\n          primary\n        }\n        furl\n      }\n    }\n    getLatestArticles(brand: $brand, count: $maxArticles) {\n      id\n      title\n      subtitle\n      furl\n      rating\n      hasVideo\n      hasGallery\n      excerpt\n      heroImage {\n        image {\n          fileName\n          path\n          width\n          height\n        }\n        altText\n        description\n        credits\n      }\n      categories {\n        parent {\n          name\n          furl\n        }\n        name\n        furl\n      }\n      publicationDate\n      heroImage {\n        image {\n          fileName\n          path\n          width\n          height\n        }\n        altText\n        description\n        credits\n      }\n      _layout {\n        content {\n          image {\n            fileName\n            path\n            width\n            height\n          }\n        }\n        handles {\n          width\n          height\n          x\n          y\n          x2\n          y2\n          _field\n        }\n        type\n      }\n      urls\n      publications {\n        hostname {\n          primary\n        }\n        furl\n      }\n    }\n    getMovies: getArticlesByCategoryWithMetaData(\n      parentCategory: $categoryMovies\n      count: $maxArticles\n      page: 1\n      brand: $brand\n    ) {\n      articles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n        excerpt\n      }\n    }\n    getReviews: getArticlesByCategoryWithMetaData(\n      parentCategory: $categoryMovies\n      subCategory: $subCategoryReviews\n      count: $maxArticles\n      page: 1\n      brand: $brand\n    ) {\n      articles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n        excerpt\n      }\n    }\n    getFeatures: getArticlesByCategoryWithMetaData(\n      parentCategory: $categoryMovies\n      subCategory: $subCategoryFeatures\n      count: $maxArticles\n      page: 1\n      brand: $brand\n    ) {\n      articles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n        excerpt\n      }\n    }\n    getTv: getArticlesByCategoryWithMetaData(parentCategory: $categoryTv, count: $maxArticles, page: 1, brand: $brand) {\n      articles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n        excerpt\n      }\n    }\n    getGaming: getArticlesByCategoryWithMetaData(\n      parentCategory: $categoryGaming\n      count: $maxArticles\n      page: 1\n      brand: $brand\n    ) {\n      articles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n        excerpt\n      }\n    }\n    getShopping: getArticlesByCategoryWithMetaData(\n      parentCategory: $categoryShopping\n      count: $maxArticles\n      page: 1\n      brand: $brand\n    ) {\n      articles {\n        id\n        title\n        furl\n        urlOverride\n        publicationDate\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n        excerpt\n      }\n    }\n    getCategoriesSubCategoriesByBrand(brand: $brand) {\n      name\n      furl\n      subCategories {\n        name\n        furl\n      }\n    }\n  }\n"}
    next_data = utils.post_url('https://publishgql.onebauer.media', json_data=post_data)
    if not next_data:
        return None
    return next_data['data']['getLatestArticles']


def get_articles_by_category(category):
    post_data = {
        "variables": {"category": category, "count": 10, "page": 1, "section": "article", "brand": "empire", "hostname": "https://www.empireonline.com"},
        "query": "\n  query getArticles(\n    $brand: String!\n    $category: String!\n    $count: Int!\n    $hostname: String!\n    $section: String!\n    $page: Int!\n  ) {\n    getMetaTemplate(brand: $brand, hostname: $hostname, section: $section) {\n      meta_title\n      meta_description\n    }\n    getArticlesByCategoryWithMetaData(parentCategory: $category, count: $count, page: $page, brand: $brand) {\n      articles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        excerpt\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n      }\n      metaData {\n        page\n        totalPages\n      }\n    }\n\n    getCategoryByBrand(brand: $brand, category: $category, count: $count, page: $page) {\n      name\n      furl\n      subCategories {\n        name\n        furl\n      }\n    }\n  }\n"}
    next_data = utils.post_url('https://publishgql.onebauer.media', json_data=post_data)
    if not next_data:
        return None
    return next_data['data']['getArticlesByCategoryWithMetaData']['articles']

def get_articles_by_subcategory(category, subcategory):
    post_data = {
        "variables":{"category": category, "subCategory": subcategory, "count": 10, "page": 1, "section": "subCategory-{}-{}".format(category, subcategory), "brand": "empire", "hostname":"https://www.empireonline.com"},
        "query": "\n  query getArticles(\n    $brand: String!\n    $category: String!\n    $subCategory: String!\n    $count: Int!\n    $hostname: String!\n    $section: String!\n    $page: Int!\n  ) {\n    getMetaTemplate(brand: $brand, hostname: $hostname, section: $section) {\n      meta_title\n      meta_description\n    }\n    getArticlesByCategoryWithMetaData(\n      parentCategory: $category\n      subCategory: $subCategory\n      count: $count\n      page: $page\n      brand: $brand\n    ) {\n      articles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        excerpt\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        publications {\n          hostname {\n            primary\n          }\n          furl\n        }\n        hasGallery\n        hasVideo\n      }\n      metaData {\n        page\n        totalPages\n      }\n    }\n\n    getSubCategoryByBrand(brand: $brand, category: $category, subCategory: $subCategory, count: $count, page: $page) {\n      name\n      furl\n      subCategories {\n        name\n        furl\n      }\n    }\n  }\n"}
    next_data = utils.post_url('https://publishgql.onebauer.media', json_data=post_data)
    if not next_data:
        return None
    return next_data['data']['getArticlesByCategoryWithMetaData']['articles']


def get_review(url):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    post_data = {
        "variables": {"furl": paths[2], "category": paths[0], "subCategory": paths[1], "hostname":"https://www.empireonline.com", "section":"review-movies", "brand":"empire", "maxRelatedArticles": 3},
        "query": "\n  query getArticleAndMetaQuery(\n    $furl: String!\n    $category: String!\n    $subCategory: String!\n    $hostname: String!\n    $section: String!\n    $brand: String!\n  ) {\n    getMetaTemplate(hostname: $hostname, section: $section, brand: $brand) {\n      meta_description\n      meta_title\n    }\n    getReviewByFurl(brand: $brand, furl: $furl, category: $category, subCategory: $subCategory) {\n      id\n      publicationDate\n      lastModifiedAt\n      furl\n      title\n      subtitle\n      isAdvertorial\n      isWordpressSite\n      sourceUrl\n      sourceText\n      seo {\n        index\n        follow\n      }\n      author {\n        id\n        fullname\n        furl\n        urlOverride\n        published {\n          state\n        }\n      }\n      author_custom\n      categories {\n        id\n        name\n        furl\n        parent {\n          id\n          name\n          furl\n        }\n      }\n      sponsor {\n        url\n        name\n        images {\n          id\n          image {\n            name\n            fileName\n            width\n            height\n            path\n          }\n        }\n      }\n      _layout {\n        content {\n          text\n          items\n          url\n          provider\n          image {\n            fileName\n            path\n            width\n            height\n          }\n          title\n          caption\n          altText\n          credits\n          price\n          amazonId\n          amazonAward\n          description\n          actionLink\n          actionText\n          coverImage {\n            image {\n              name\n              fileName\n              path\n              width\n              height\n            }\n            titleText\n            altText\n            credits\n            description\n            orientation\n            caption\n            actionText\n            actionLink\n          }\n          template\n          images {\n            id\n            image {\n              name\n              fileName\n              path\n              width\n              height\n            }\n            titleText\n            altText\n            credits\n            description\n            orientation\n            caption\n            actionText\n            actionLink\n            amazonId\n            price\n          }\n        }\n        handles {\n          width\n          height\n          x\n          y\n          x2\n          y2\n          _field\n        }\n        type\n      }\n      excerpt\n      heroImage {\n        id\n        altText\n        credits\n        caption\n        image {\n          fileName\n          name\n          width\n          height\n          path\n        }\n      }\n      metaTitle\n      metaDescription\n      hasAmazonProduct\n      hasAmazonLinkOnPage\n      hasGallery\n      hasProduct\n      campaign_name\n      display_ads_gam\n      display_skimlinks\n      display_gumgum\n      pageTemplate\n      hasVideo\n      pictureCount\n      people {\n        name\n        furl\n      }\n      heroImageSize\n\n      film {\n        title\n        originalTitle\n        certificate\n        running_time\n        website\n        releaseDate\n        tmdbId\n        furl\n      }\n      tv {\n        title\n        tmdbId\n        furl\n      }\n      game {\n        title\n        furl\n      }\n      people {\n        name\n        furl\n      }\n      verdict\n      rating\n      nutshell\n      relatedArticles {\n        id\n        title\n        furl\n        rating\n        urlOverride\n        publicationDate\n        heroImage {\n          image {\n            name\n            fileName\n            mimeType\n            path\n          }\n          altText\n        }\n        categories {\n          name\n          furl\n          parent {\n            name\n            furl\n          }\n        }\n        urls\n        hasGallery\n        hasVideo\n      }\n    }\n  }\n"}
    next_data = utils.post_url('https://gql.bauerhosting.com/', json_data=post_data)
    if not next_data:
        return None
    return next_data['data']['getReviewByFurl']


def get_article(url):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    post_data = {
        "variables": {"furl": paths[2], "category": paths[0], "subCategory": paths[1], "hostname":"https://www.empireonline.com", "section":"article", "brand":"empire"},
        "query": "\n  query getArticleAndMetaQuery(\n    $furl: String!\n    $category: String!\n    $subCategory: String!\n    $hostname: String!\n    $section: String!\n    $brand: String!\n  ) {\n    getMetaTemplate(hostname: $hostname, section: $section, brand: $brand) {\n      meta_description\n      meta_title\n    }\n    getArticleByFurl(brand: $brand, furl: $furl, category: $category, subCategory: $subCategory) {\n      id\n      publicationDate\n      lastModifiedAt\n      furl\n      title\n      subtitle\n      isAdvertorial\n      isWordpressSite\n      sourceUrl\n      sourceText\n      seo {\n        index\n        follow\n      }\n      author {\n        id\n        fullname\n        furl\n        urlOverride\n        published {\n          state\n        }\n      }\n      author_custom\n      categories {\n        id\n        name\n        furl\n        parent {\n          id\n          name\n          furl\n        }\n      }\n      sponsor {\n        url\n        name\n        images {\n          id\n          image {\n            name\n            fileName\n            width\n            height\n            path\n          }\n        }\n      }\n      _layout {\n        content {\n          text\n          items\n          url\n          provider\n          image {\n            fileName\n            path\n            width\n            height\n          }\n          title\n          caption\n          altText\n          credits\n          price\n          amazonId\n          amazonAward\n          description\n          actionLink\n          actionText\n          coverImage {\n            image {\n              name\n              fileName\n              path\n              width\n              height\n            }\n            titleText\n            altText\n            credits\n            description\n            orientation\n            caption\n            actionText\n            actionLink\n          }\n          template\n          images {\n            id\n            image {\n              name\n              fileName\n              path\n              width\n              height\n            }\n            titleText\n            altText\n            credits\n            description\n            orientation\n            caption\n            actionText\n            actionLink\n            amazonId\n            price\n          }\n        }\n        handles {\n          width\n          height\n          x\n          y\n          x2\n          y2\n          _field\n        }\n        type\n      }\n      excerpt\n      heroImage {\n        id\n        altText\n        credits\n        caption\n        image {\n          fileName\n          name\n          width\n          height\n          path\n        }\n      }\n      metaTitle\n      metaDescription\n      hasAmazonProduct\n      hasAmazonLinkOnPage\n      hasGallery\n      hasProduct\n      campaign_name\n      display_ads_gam\n      display_skimlinks\n      display_gumgum\n      pageTemplate\n      product {\n        rating\n        rrp\n        brand\n        amazon_product_id\n        product_url\n      }\n      hasVideo\n      pictureCount\n      people {\n        name\n        furl\n      }\n    }\n  }\n"
    }
    next_data = utils.post_url('https://gql.bauerhosting.com/', json_data=post_data)
    if not next_data:
        return None
    return next_data['data']['getArticleByFurl']


def get_next_data(url, save_debug=False):
    article_html = utils.get_url_html(url)
    if not article_html:
        return None
    soup = BeautifulSoup(article_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    next_data = json.loads(el.string)
    return next_data['props']['pageProps']


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'reviews' in paths:
        is_review = True
        article_json = get_review(url)
        if not article_json:
            return None
    else:
        is_review = False
        article_json = get_article(url)
        if not article_json:
            return None

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    if article_json.get('canonical'):
        item['url'] = article_json['canonical']
    else:
        item['url'] = utils.clean_url(url)
    item['title'] = article_json['title']
    if is_review:
        item['title'] += ' Review'

    dt = datetime.fromtimestamp(article_json['publicationDate']/1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('lastModifiedAt'):
        dt = datetime.fromtimestamp(article_json['lastModifiedAt']/1000).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('author') and article_json['author'].get('fullname'):
        item['author']['name'] = article_json['author']['fullname']
    elif article_json.get('author_custom'):
        item['author']['name'] = article_json['author_custom']

    item['tags'] = []
    if article_json.get('categories'):
        for cat in article_json['categories']:
            if cat.get('parent'):
                tag = cat['parent']['name']
                if not tag.casefold() in (it.casefold() for it in item['tags']):
                    item['tags'].append(tag)
            tag = cat['name']
            if not tag.casefold() in (it.casefold() for it in item['tags']):
                item['tags'].append(tag)
    if len(item['tags']) == 0:
        del item['tags']

    if article_json.get('heroImage') and article_json['heroImage'][0].get('image'):
            item['_image'] = resize_image(article_json['heroImage'][0]['image'])

    item['summary'] = article_json['excerpt']

    content_html = ''
    if article_json.get('heroImage'):
        content_html += add_image(article_json['heroImage'][0])

    if is_review:
        content_html += '<p><strong>{}</strong></p>'.format(article_json['nutshell'])
        if article_json.get('rating'):
            content_html += '<p>Rating: '
            rating = int(article_json['rating'])
            if rating == 5:
                content_html += '<span style="color:red;">'
            for i in range(5):
                if i < rating:
                    content_html += '&#9733;'
                else:
                    content_html += '&#9734;'
            if rating == 5:
                content_html += '</span>'
            content_html += '</p>'
        if article_json.get('film') and article_json['film'][0].get('releaseDate'):
            dt = datetime.fromtimestamp(article_json['film'][0]['releaseDate']/1000)
            content_html += '<p>Release date: {}. {}, {}</p>'.format(dt.strftime('%b'), dt.day, dt.year)

    for layout in article_json['_layout']:
        if layout['type'] == 'content':
            #soup = BeautifulSoup(markdown(layout['content']['text'].replace('{:target=_blank}', '')), 'html.parser')
            #content_html += str(soup)
            text = re.sub(r'{:target=[^}]+}', '', layout['content']['text'])
            content_html += markdown(text)

        elif layout['type'] == 'title':
            continue

        elif layout['type'] == 'subtitle':
            content_html += '<h4>{}</h4>'.format(layout['content']['text'])

        elif layout['type'] == 'heroImage' or layout['type'] == 'images':
            content_html += add_image(layout['content'])

        elif layout['type'] == 'pullQuotes':
            text = re.sub(r'^> ', '', layout['content']['text'])
            content_html += utils.add_pullquote(text)

        elif layout['type'] == 'embeds':
            content_html += utils.add_embed(layout['content']['url'])

        elif layout['type'] == 'imageGalleries':
            content_html += '<h3>{}</h3>'.format(layout['content']['title'])
            for image in layout['content']['images']:
                content_html += '<h3>{}</h3>'.format(image['titleText'])
                content_html += add_image(image)
                if image['description'].endswith('<br>'):
                    desc = image['description'][:-4]
                else:
                    desc = image['description']
                desc = re.sub(r'{:target=[^}]+}', '', desc)
                content_html += '<p>{}'.format(markdown(desc))
                if image.get('actionLink'):
                    content_html += '<br/><br/>£{} from <a href="{}">{}</a>'.format(image['price'], image['actionLink'], image['actionText'])
                content_html += '</p><hr/>'

        elif layout['type'] == 'tags':
            if not all(val == None for val in layout['content'].values()):
                logger.warning('unhandled laout type tags in ' + item['url'])

        else:
            logger.warning('unhandled layout type {} in {}'.format(layout['type'], item['url']))

    if is_review:
        content_html += '<p><strong>{}</strong></p>'.format(article_json['verdict'])

    item['content_html'] = content_html
    return item


def get_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0:
        articles = get_latest_articles()
    elif len(paths) == 1:
        articles = get_articles_by_category(paths[0])
    else:
        articles = get_articles_by_subcategory(paths[0], paths[1])

    if save_debug:
        utils.write_file(articles, './debug/feed.json')

    n = 0
    items = []
    for article in articles:
        if article.get('canonical'):
            url = article['canonical']
        else:
            url = re.sub(r'^{}'.format(article['publications'][0]['furl']), article['publications'][0]['hostname']['primary'], article['urls'][0])
        if save_debug:
            logger.debug('getting contents for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed