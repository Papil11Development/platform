from settings import (APP_VERSION, TERMS_URL, CONTACT_URL, CONTACT_NAME,
                      UNIT_TYPE, CONTACT_PRODUCT_NAME, PROCESSING_DEPENDENCIES)


def get_app_description() -> dict:
    description = ""
    if PROCESSING_DEPENDENCIES:
        description += f"\nDependencies: {' -> '.join(PROCESSING_DEPENDENCIES)}"

    title = UNIT_TYPE.replace("_", " ").title().replace(" ", "")
    app_description = {
        'title': title,
        'description': description,
        'version': APP_VERSION
    }

    app_description.update({
        'title': f'{CONTACT_PRODUCT_NAME} {title}',
        'terms_of_service': TERMS_URL,
        'contact': {
            'name': CONTACT_NAME,
            'url': CONTACT_URL,
            # 'email': '',
        },
        # 'license_info': {
        #     'name': '',
        #     'url': '',
        # }
    })

    return app_description
