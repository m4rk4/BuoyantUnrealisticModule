import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(dict_images, width=1200):
    images = []
    for key, val in dict_images.items():
        if not val:
            continue
        m = re.search(r'\d+$', key)
        if m:
            val['width'] = int(m.group(0))
            images.append(val)
    image = utils.closest_dict(images, 'width', width)
    return image['src']


def get_video_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    uuid = paths[-1].split('-')[-1]
    embed_url = 'https://stream24.ilsole24ore.com/embed/' + uuid
    page_html = utils.get_url_html(embed_url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'^__NEXT_DATA__'))
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + embed_url)
        return None
    i = el.string.find('{')
    j = el.string.find('};__NEXT') + 1
    next_data = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    video_json = next_data['props']['pageProps']['dataVideoLeaf']['videoLeaf']
    item = {}
    item['id'] = video_json['uuid']
    item['url'] = 'https://stream24.ilsole24ore.com' + video_json['url']
    item['title'] = video_json['title']['leafTitle']

    el = soup.find('meta', attrs={"property": "article:published_time"})
    if el:
        dt = datetime.fromisoformat(el['content'])
    elif video_json.get('createdAt'):
        dt = datetime.fromtimestamp(int(video_json['createdAt']) / 1000).astimezone(pytz.timezone('Europe/Rome'))
    else:
        dt = None
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if video_json.get('signature'):
        item['author'] = {
            "name": video_json['signature']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    if video_json.get('imageWide'):
        item['image'] = resize_image(video_json['imageWide'])
    elif video_json.get('cover'):
        item['image'] = video_json['cover']['large']

    if video_json.get('text'):
        item['summary'] = video_json['text']

    el = soup.find('video-js')
    if el:
        bc_url = 'https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(next_data['runtimeConfig']['brightcovePlayerAccount'], next_data['runtimeConfig']['brightcovePlayerVideo'], quote(el['data-video-id']))
        item['content_html'] = utils.add_embed(bc_url)
    else:
        logger.warning('unable to find video-js in ' + embed_url)

    if ('embed' not in args or '/embed/' not in url) and 'summary' in item:
        item['content_html'] += '<p>' + item['summary'] + '</p>'

    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'video' in paths:
        return get_video_content(url, args, site_json, save_debug)

    uuid = paths[-1].split('-')[-1]
    # print(uuid)
    if split_url.netloc == '24plus.ilsole24ore.com':
        data = {
            "operationName": "foglia24Plus",
            "variables": {
                "fAG": False,
                "limitSfide": 7,
                "swgProductID": "24plus.ilsole24ore.com:basic",
                "uuid": uuid
            },
            "query": "fragment BaseArticleGallery on ArticleGallery {\n  uuid\n  slug\n  title {\n    leafTitle\n    __typename\n  }\n  menu {\n    uuid\n    slug\n    title {\n      leafTitle\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment BaseDossier on Dossier {\n  uuid\n  sectionId\n  subsectionId\n  label\n  slug\n  parentUuid\n  parentSlug\n  title {\n    leafTitle\n    __typename\n  }\n  __typename\n}\n\nfragment BaseAuthor on Author {\n  title\n  uuid\n  place\n  role\n  socialPages {\n    twitter\n    linkedin\n    email\n    __typename\n  }\n  avatar {\n    imagepath70 {\n      src\n      __typename\n    }\n    __typename\n  }\n  languages\n  arguments\n  prizes\n  authorPage\n  __typename\n}\n\nfragment ImagesWide on Article {\n  rectangleMasterFoto {\n    src\n    alt\n    __typename\n  }\n  posterMasterFoto {\n    src\n    alt\n    __typename\n  }\n  imageWide {\n    image1440 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  imageWide {\n    image1170 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  imageWide {\n    image835 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  imageWide {\n    image672 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  imageWide {\n    image403 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  imageWide {\n    image310 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  imageWide {\n    image237 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  imageWide {\n    image154 {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment ImagesTags on Article {\n  squaredMasterFoto {\n    src\n    alt\n    __typename\n  }\n  rectangleMasterFoto {\n    src\n    alt\n    __typename\n  }\n  posterMasterFoto {\n    src\n    alt\n    __typename\n  }\n  imageWide {\n    image1440 {\n      src\n      __typename\n    }\n    __typename\n  }\n  imageSquare {\n    image735 {\n      src\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment openings on EmbedContent {\n  uuid\n  type\n  ... on Content {\n    section\n    sectionId\n    subsection\n    subsectionId\n    subhead\n    slug\n    slugDate\n    title {\n      leafTitle\n      __typename\n    }\n    __typename\n  }\n  ... on Gallery {\n    url\n    cover {\n      big\n      __typename\n    }\n    json {\n      uuid\n      deepurl\n      sezione\n      title\n      images {\n        title\n        caption\n        large\n        src\n        __typename\n      }\n      __typename\n    }\n    photoNumber\n    __typename\n  }\n  ... on Video {\n    caption\n    duration\n    titolo\n    sommario\n    dida\n    __typename\n  }\n  __typename\n}\n\nfragment embeds on EmbedContent {\n  ...openings\n  ... on Audio {\n    parentRubrica {\n      uuid\n      rubricaId\n      __typename\n    }\n    signature\n    title {\n      leadTitle {\n        href\n        text\n        target\n        __typename\n      }\n      __typename\n    }\n    url\n    caption\n    videoData {\n      embedded\n      id\n      embedCode\n      manageOnAir\n      urlPodcast\n      __typename\n    }\n    __typename\n  }\n  ... on Podcast {\n    parentRubrica {\n      uuid\n      rubricaId\n      __typename\n    }\n    signature\n    title {\n      leafTitle\n      __typename\n    }\n    url\n    caption\n    videoData {\n      embedded\n      id\n      embedCode\n      manageOnAir\n      urlPodcast\n      __typename\n    }\n    __typename\n  }\n  ... on Social {\n    user\n    tweetid\n    __typename\n  }\n  ... on Chart {\n    title {\n      leafTitle\n      __typename\n    }\n    dataHTML\n    dataURL\n    leadText\n    didascalia\n    __typename\n  }\n  ... on GalleryInline {\n    insertType\n    title {\n      leafTitle\n      __typename\n    }\n    cover {\n      big\n      __typename\n    }\n    json {\n      uuid\n      title\n      images: inlineImages {\n        caption\n        credit\n        src\n        large: src\n        __typename\n      }\n      __typename\n    }\n    photoNumber\n    __typename\n  }\n  ... on Quote {\n    text\n    signature\n    role\n    __typename\n  }\n  ... on Comment {\n    text\n    signature\n    titolo\n    date\n    imgFileref\n    __typename\n  }\n  ... on Image {\n    src\n    alt\n    caption\n    titolo\n    sommario\n    __typename\n  }\n  ... on Document {\n    subhead\n    title {\n      leafTitle\n      __typename\n    }\n    url\n    __typename\n  }\n  ... on Creativity {\n    titleCreativity: title {\n      leafTitle(noDummyTitle: true)\n      __typename\n    }\n    summary\n    leadText\n    dataHTML\n    didaCreativity: summaryLead {\n      text\n      __typename\n    }\n    __typename\n  }\n  ... on OEmbed {\n    uuid\n    titleCreativity: title {\n      leafTitle(noDummyTitle: true)\n      __typename\n    }\n    summary\n    dataHTML\n    embedType\n    embedSrc\n    __typename\n  }\n  ... on Map {\n    title {\n      leafTitle\n      __typename\n    }\n    dataHTML\n    leadText\n    __typename\n  }\n  ... on RelatedEmbed {\n    titolo\n    testolink\n    link\n    image {\n      src\n      alt\n      __typename\n    }\n    __typename\n  }\n  ... on ArticleGroupProfessionisti {\n    articles {\n      uuid\n      url\n      title {\n        leafTitle\n        __typename\n      }\n      squaredMasterFoto {\n        src\n        alt\n        __typename\n      }\n      slug\n      isNTPFisco\n      isNTPDiritto\n      isNTPEdiliziaPa\n      isNTPCondominio\n      isNTPLavoro\n      type\n      webtype\n      sectionId\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment BaseArticle on Article {\n  uuid\n  section\n  sectionId\n  subsectionId\n  subhead\n  slug\n  slugDate\n  subwebtype\n  webtype\n  pay\n  __typename\n}\n\nquery foglia24Plus($uuid: String, $limitSfide: Int, $swgProductID: String, $fAG: Boolean) {\n  article(uuid: $uuid) {\n    specialSummary {\n      title {\n        text\n        __typename\n      }\n      keyPoints {\n        text\n        __typename\n      }\n      __typename\n    }\n    articleGallery {\n      ...BaseArticleGallery\n      __typename\n    }\n    ...BaseArticle\n    frontendTemplate\n    section\n    subsection\n    subsectionId\n    webtype\n    subwebtype\n    createdAt\n    updatedAt\n    trusted\n    trustedPayload(swgProductID: $swgProductID)\n    showUpdated\n    showListing\n    showCopyright\n    showPhoto\n    noindex\n    readingtime\n    signature\n    commentsNumber\n    summary\n    subhead\n    url\n    codicekbbar\n    dossier24plus {\n      ...BaseDossier\n      intro {\n        subhead\n        subwebtype\n        __typename\n      }\n      __typename\n    }\n    authors {\n      ...BaseAuthor\n      __typename\n    }\n    tagAuthors\n    opening {\n      ...openings\n      __typename\n    }\n    title {\n      leafTitle\n      __typename\n    }\n    tags {\n      uuid\n      tagname\n      url\n      __typename\n    }\n    text(fAG: $fAG) {\n      text\n      embed {\n        ...embeds\n        __typename\n      }\n      node\n      __typename\n    }\n    imageSquare {\n      image95 {\n        src\n        alt\n        __typename\n      }\n      image390 {\n        src\n        alt\n        __typename\n      }\n      __typename\n    }\n    ...ImagesWide\n    ...ImagesTags\n    imageWide {\n      image1260 {\n        src\n        alt\n        __typename\n      }\n      image1020 {\n        src\n        alt\n        __typename\n      }\n      __typename\n    }\n    finCodes\n    taxonomyInfo {\n      adunit\n      __typename\n    }\n    metaDescription\n    dossier {\n      ...BaseDossier\n      menu {\n        ...BaseDossier\n        __typename\n      }\n      __typename\n    }\n    commentsConfig {\n      showBox\n      allowComments\n      characters\n      __typename\n    }\n    sfida {\n      uuid\n      intro {\n        uuid\n        slug\n        shortTitle\n        title {\n          leadTitle {\n            text\n            __typename\n          }\n          leafTitle\n          __typename\n        }\n        __typename\n      }\n      items(limit: 3, exclude: [$uuid]) {\n        items {\n          uuid\n          title {\n            leadTitle {\n              text\n              __typename\n            }\n            __typename\n          }\n          subhead\n          subsection\n          subsectionId\n          createdAt\n          webtype\n          imageSquare {\n            image71 {\n              src\n              alt\n              __typename\n            }\n            __typename\n          }\n          url\n          slug\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    relatedGroup {\n      label\n      related {\n        titolo\n        testolink\n        link\n        image {\n          src\n          alt\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    audioReadingIsPresent\n    audioReading {\n      ... on Audio {\n        signature\n        title {\n          leafTitle\n          leadTitle {\n            href\n            target\n            text\n            __typename\n          }\n          __typename\n        }\n        url\n        uuid\n        caption\n        imageSquare {\n          image71 {\n            src\n            __typename\n          }\n          __typename\n        }\n        videoData {\n          embedded\n          id\n          embedCode\n          manageOnAir\n          urlPodcast\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    payWall {\n      locked\n      docRulesView\n      subscription {\n        active\n        productsList\n        __typename\n      }\n      oneShot {\n        active\n        productsList\n        __typename\n      }\n      freeForce\n      __typename\n    }\n    articleGroupEnding {\n      key\n      label\n      articles {\n        uuid\n        url\n        title {\n          leafTitle\n          __typename\n        }\n        squaredMasterFoto {\n          src\n          alt\n          __typename\n        }\n        slug\n        isNTPFisco\n        isNTPDiritto\n        isNTPEdiliziaPa\n        isNTPCondominio\n        isNTPLavoro\n        type\n        webtype\n        sectionId\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  sfide(limit: $limitSfide) {\n    items {\n      uuid\n      count\n      intro {\n        uuid\n        shortTitle\n        title {\n          leafTitle\n          leadTitle {\n            text\n            __typename\n          }\n          __typename\n        }\n        imageTall {\n          image625 {\n            src\n            alt\n            __typename\n          }\n          image420 {\n            src\n            alt\n            __typename\n          }\n          __typename\n        }\n        url\n        slug\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  audioReadingList(limit: 5) {\n    items {\n      uuid\n      title {\n        leadTitle {\n          text\n          href\n          __typename\n        }\n        __typename\n      }\n      subhead\n      subsectionId\n      subsection\n      signature\n      imageSquare {\n        image390 {\n          src\n          __typename\n        }\n        __typename\n      }\n      audioReadingIsPresent\n      audioReading {\n        uuid\n        duration\n        title {\n          leafTitle\n          __typename\n        }\n        videoData {\n          id\n          uuid\n          urlPodcast\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
        }
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": "\"Chromium\";v=\"136\", \"Microsoft Edge\";v=\"136\", \"Not.A/Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-nile-client": "24plus",
            "x-nile-product-service": "OLC/SITOPAY"
        }
        gql_json = utils.post_url('https://24plus.ilsole24ore.com/api/graphql', json_data=data, headers=headers)
    else:
        data = {
            "operationName": "fogliaDotcom",
            "variables": {
                "uuid": uuid
            },
            "query": "\n\nfragment BaseArticle on Article {\n  uuid\n  section\n  sectionId\n  subsectionId\n  subhead\n  slug\n  slugIT\n  slugEN\n  slugDate\n  subwebtype\n  webtype\n  payWall{\n    title\n    docRulesView\n    subscription{\n      active\n      productsList\n    }\n    oneShot{\n      active\n      productsList\n      paymentCode\n      shoppingCode\n    }\n    freeForce\n  }\n}\n\nfragment openings on EmbedContent {\n  uuid\n  type\n  ...on Content {\n    section\n    sectionId\n    subsection\n    subsectionId\n    subhead\n    slug\n    slugDate\n    title {\n      leafTitle\n    }\n  }\n  ...on Gallery {\n    url\n    cover {\n      big\n    }\n    photoNumber\n  }\n  ...on Video {\n    caption\n    duration\n  }\n}\nfragment embeds on EmbedContent {\n  ...openings\n  ...on Audio {\n    title {\n      leadTitle {\n        href\n        text\n        target\n      }\n    }\n    url\n    caption\n    videoData {\n      embedded\n      id\n      embedCode\n      manageOnAir\n      urlPodcast\n    }\n  }\n  ...on Podcast {\n    title {\n      leadTitle {\n        href\n        text\n        target\n      }\n    }\n    url\n    caption\n    videoData {\n      embedded\n      id\n      embedCode\n      manageOnAir\n      urlPodcast\n    }\n  }\n  ...on GalleryInline {\n    title {\n      leafTitle\n    }\n    cover {\n      big\n    }\n    photoNumber\n  }\n  ...on Social {\n    user\n    tweetid\n  }\n  ...on Chart {\n    insertType\n    title {\n      leafTitle\n    }\n    titleChart: title {\n      leafTitle(noDummyTitle: true)\n    }\n    dataHTML\n    dataURL\n    leadText\n    didascalia\n  }\n  ...on Quote {\n    text\n    signature\n    role\n  }\n  ...on Image {\n    src\n    alt\n    caption\n    titolo\n    sommario\n  }\n  ...on Document {\n    subhead\n    title {\n      leafTitle\n    }\n    url\n  }\n  ...on Creativity {\n    titleCreativity: title {\n      leafTitle(noDummyTitle: true)\n    }\n    leadText\n    summary\n    dataHTML\n    didaCreativity: summaryLead {\n      text\n    }\n  }\n  ...on Map {\n    title {\n      leafTitle\n    }\n    dataHTML\n    leadText\n  }\n  ... on RelatedEmbed {\n    titolo\n    testolink\n    link\n    image {\n      src\n      alt\n    }\n  }\n  ... on ArticleGroup {\n    uuid\n    type\n    key\n    articles {\n      uuid\n      url\n      type\n      section\n      sectionId\n      subsection\n      subsectionId\n      subhead\n      slug\n      createdAt\n      isNTPFisco\n      isNTPDiritto\n      isNTPEdiliziaPa\n      isNTPCondominio\n      isNTPLavoro\n      pay\n      webtype\n      dossier {\n        ...BaseDossier\n      }\n      title {\n        leafTitle\n      }\n      imageSquare{\n        image258{\n          src\n          alt\n         }\n      }\n      imageWide {\n        image403 {\n            src\n            alt\n         }\n      }\n      payWall {\n        docRulesView\n        subscription{\n          active\n          productsList\n        }\n        oneShot{\n          active\n          productsList\n        }\n      }\n    }\n  }\n  ... on ThematicBox {\n    type\n    title {\n      leafTitle\n    }\n    blocks {\n      type\n      paragraph {\n        text\n        embed {\n          ...on Image {\n            src\n            alt\n            caption\n            icon\n            link\n          }\n        }\n      }\n    }\n  }\n  ... on OEmbed {\n    uuid\n    titleCreativity: title {\n      leafTitle(noDummyTitle: true)\n    }\n    summary\n    dataHTML\n    embedType\n    embedSrc\n  }\n  ... on Article {\n    isNTPFisco\n    isNTPDiritto\n    isNTPEdiliziaPa\n    isNTPCondominio\n    isNTPLavoro\n    dossier {\n      ...BaseDossier\n    }\n    pay\n    url\n    webtype\n    type\n    payWall {\n      docRulesView\n      subscription{\n        active\n        productsList\n      }\n      oneShot{\n        active\n        productsList\n      }\n    }\n  }\n}\n\n\nfragment ImagesWide on Article {\n  imageWide {\n    image1170 {\n      src\n      alt\n    }\n  }\n  imageWide {\n    image835 {\n      src\n      alt\n    }\n  }\n  imageWide {\n    image672 {\n      src\n      alt\n    }\n  }\n  imageWide {\n    image403 {\n      src\n      alt\n    }\n  }\n  imageWide {\n    image310 {\n      src\n      alt\n    }\n  }\n  imageWide {\n    image237 {\n      src\n      alt\n    }\n  }\n  imageWide {\n    image154 {\n      src\n      alt\n    }\n  }\n}\n\n\nfragment BaseAuthor on Author {\n  title\n  uuid\n  place\n  role\n  socialPages{\n    twitter\n    linkedin\n    email\n  }\n  avatar{\n    imagepath70{\n      src\n    }\n  }\n  languages\n  arguments\n  prizes\n  authorPage\n}\n\n\nfragment BaseDossier on Dossier {\n  uuid\n  sectionId\n  subsectionId\n  label\n  slug\n  parentUuid\n  parentSlug\n  title{\n    leafTitle\n  }\n}\n\nfragment BaseArticleGallery on ArticleGallery {\n      uuid\n      slug\n      title{\n        leafTitle\n      }\n\t\t\tmenu{\n        uuid\n        slug\n        title{\n          leafTitle\n        }\n      }\n    }\n\nfragment BaseEbookCover on EbookCover {\n  uuid\n  sectionId\n  section\n  subsectionId\n  subsection\n  slug\n  title{\n    leafTitle\n  }\n  \n}\nquery fogliaDotcom($uuid: String, $force: Boolean = false, $mobile: Boolean = false){\n  article(uuid: $uuid, force: $force) {\n    articleGallery{\n      ...BaseArticleGallery\n    }\n    ...BaseArticle\n    frontendTemplate\n    version\n    section\n    subsection\n    subsectionId\n    webtype\n    subwebtype\n    createdAt\n    updatedAt\n    trusted\n    trustedPayload\n    updateDate\n    showListing\n    showCopyright\n    showPhoto\n    noindex\n    readingtime\n    signature\n    commentsNumber\n    eyeletMasterFoto {\n      src\n      alt\n    }\n    posterMasterFoto {\n      src\n      alt\n    }\n    rectangleMasterFoto {\n      src \n      alt\n    }\n    squaredMasterFoto {\n      src \n      alt\n    }\n    commentsNumber\n    summary\n    subhead\n    url\n    codicekbbar\n    authors{\n      ...BaseAuthor\n    }\n    tagAuthors\n    opening{\n      ...openings\n    }\n    title{\n      leafTitle\n    }\n    specialSummary {\n      title {\n        text\n      }\n      keyPoints {\n        text\n      }\n    }\n    revision {\n      title {\n        text\n      }\n      paragraphs {\n        text\n      }\n    }\n    tags{\n      uuid\n      tagname\n      url\n    }\n    text{\n      text\n      embed {\n        ...embeds\n      }\n      node\n    }\n    relatedGroup {\n      label\n      related {\n        titolo\n        link\n      } \n    }\n    ...ImagesWide\n    imageWide {\n      image1260 {\n        src\n        alt\n      }\n      image1020 {\n        src\n        alt\n      }\n    }\n    imageSquare {\n      image95 {\n        src\n      }\n    }\n    finCodes\n    mailToRedazione\n    liveFragments {\n      id\n      time\n      date\n      title\n      titleId\n      pos\n      name\n      author\n      pinned\n      timestampPostLive\n      fragmentGroupEnding{\n        articles{\n          ...BaseArticle\n          slugDate\n          title {\n            leafTitle\n          }\n          squaredMasterFoto{\n            alt\n            src\n          }\n        }\n      }\n      text {\n        text\n        embed {\n          ...embeds\n        }\n        node\n      }\n    }\n    taxonomyInfo {\n      adunit\n      nielsenAppID\n      nielsenSection\n    }\n    metaDescription\n    dossier {\n      ...BaseDossier\n      intro {\n        subhead\n        subwebtype\n      }\n      type\n      menu {\n        label\n        slug\n        uuid\n        url\n        menuType\n      }\n      menuSuperDossier {\n        label\n        slug\n        uuid\n        url\n        menuType\n      }\n    }\n    ebookCover {\n      ...BaseEbookCover\n    }\n    commentsConfig {\n      showBox\n      allowComments\n      characters\n    }\n    mainDwp {\n      articleStrip\n    }\n    embedMarketing {\n      title {\n        leadTitle {\n          text\n        }\n      }\n      url\n      labelLink\n      subhead\n      squaredMasterFoto {\n        src \n        alt\n      }\n      imageSquare{\n        image258{\n          src\n        }\n      }\n    }\n    embedConsigli24 {\n      uuid\n      title {\n        leadTitle {\n          text\n        }\n      }\n      url\n      labelLink\n      subhead\n      squaredMasterFoto {\n        src \n        alt\n      }\n      imageSquare{\n        image258{\n          src\n        }\n      }\n    }\n    articleGroupEnding {\n      key\n      label\n      articles {\n        uuid\n        type\n        sectionId\n        slug\n        isNTPFisco\n        isNTPDiritto\n        isNTPEdiliziaPa\n        isNTPCondominio\n        isNTPLavoro\n        pay\n        webtype\n        url\n        title {\n          leafTitle\n        }\n        rectangleMasterFoto {\n          src \n          alt\n        }\n        imageWide {\n          image154 @skip (if:$mobile) {\n            src\n            alt\n          }\n          image310 @include (if:$mobile) {\n            src\n            alt\n          }\n        }\n        payWall {\n          docRulesView\n          subscription{\n            active\n            productsList\n          }\n          oneShot{\n            active\n            productsList\n          }\n        }\n      }\n    }\n    articleGroupProfessionisti {\n      articles {\n        uuid\n        type\n        sectionId\n        slug\n        slugDate\n        isNTPFisco\n        isNTPDiritto\n        isNTPEdiliziaPa\n        isNTPCondominio\n        isNTPLavoro\n        pay\n        webtype\n        url\n        title {\n          leafTitle\n        }\n        rectangleMasterFoto {\n          src \n          alt\n        }\n        squaredMasterFoto {\n          src \n          alt\n        }\n        imageWide {\n          image154 @skip (if:$mobile) {\n            src\n            alt\n          }\n          image310 @include (if:$mobile) {\n            src\n            alt\n          }\n        }\n        payWall {\n          docRulesView\n          subscription{\n            active\n            productsList\n          }\n          oneShot{\n            active\n            productsList\n          }\n        }\n      \n      }\n    }\n    articleManagement {\n      onAir\n    }\n    sponsorManagement {\n      url\n    }\n    isFreeArticle\n    titoloSeo {\n      text: genAIEnrichmentText\n    }\n    abstractSeo {\n      text: genAIEnrichmentText\n    }\n    audioVersion\n  }\n  \n}\n"
        }
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": "\"Chromium\";v=\"136\", \"Microsoft Edge\";v=\"136\", \"Not.A/Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "x-nile-client": "dotcom",
            "x-nile-origin": "3.41.02-prod",
            "x-nile-product-service": "OLC/SITO"
        }
        gql_json = utils.post_url('https://graph.ilsole24ore.com/', json_data=data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    article_json = gql_json['data']['article']
    ld_json = json.loads(article_json['trustedPayload'])

    item = {}
    item['id'] = article_json['uuid']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['name']} for x in ld_json['author']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    if article_json.get('tags'):
        item['tags'] = [x['tagname'] for x in article_json['tags']]
    elif ld_json.get('keywords'):
        item['tags'] = ld_json['keywords'].copy()

    item['content_html'] = ''
    if article_json.get('summary'):
        item['summary'] = article_json['summary']
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'
    elif article_json.get('metaDescription'):
        item['summary'] = article_json['metaDescription']
    elif ld_json.get('description'):
        item['summary'] = ld_json['description']

    if article_json.get('imageWide'):
        item['image'] = resize_image(article_json['imageWide'])
    elif article_json.get('rectangleMasterFoto'):
        item['image'] = article_json['rectangleMasterFoto']['src']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if article_json.get('opening') and article_json['opening']['type'] == 'video':
        video_content = get_video_content('https://stream24.ilsole24ore.com/embed/' + article_json['opening']['uuid'], {'embed': True}, site_json, False)
        if video_content:
            item['content_html'] += video_content['content_html']
    elif article_json.get('rectangleMasterFoto'):
        item['content_html'] += utils.add_image(item['image'], article_json['rectangleMasterFoto']['alt'])

    for text in article_json['text']:
        if text.get('embed'):
            if text['embed']['type'] == 'embedfotogrande':
                item['content_html'] += utils.add_image(text['embed']['src'], text['embed'].get('caption'))
            elif text['embed']['type'] == 'video':
                video_content = get_video_content('https://stream24.ilsole24ore.com/embed/' + text['embed']['uuid'], {'embed': True}, site_json, False)
                if video_content:
                    item['content_html'] += video_content['content_html']
            else:
                logger.warning('unhandled text embed {} in {}'.format(text['embed'], item['url']))
        if text.get('node'):
            if re.search(r'^<h\d', text['node']):
                item['content_html'] += text['node']
            else:
                logger.warning('unhandled text node {} in {}'.format(text['node'], item['url']))
        if text.get('text'):
            item['content_html'] += '<p>' + text['text'] + '</p>'

    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.ilsole24ore.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
