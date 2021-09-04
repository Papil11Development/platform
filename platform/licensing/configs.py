import os

products = {
    "platform-cloud-basic": {
        "period": '1m',                         # specified in plan
        "trial_period": "14d",
        "mode": "subscription",
        "meter_attributes": {
            "channels": {                       # how many cameras allowed after buying subscription
                "products": {
                    "stripe_live": os.environ.get("STRIPE_LIVE_CHANNELS_PRODUCT", ""),
                    "stripe_test": "prod_LiprPlI8T9HTzm"
                },
                "limit": -1,
                "trial_limit": 3,               # default value for trial subscription, for paid mode limit = -1
                "plans": {
                    "stripe_live": os.environ.get("STRIPE_LIVE_CHANNELS_BASIC", ""),
                    "stripe_test": "price_1L1OBzKj0lYUbKAV8ZzPyZlN"
                },
                "additional_properties": {}
            },
            "persons_in_base": {
                "products": {
                    "stripe_live": os.environ.get("STRIPE_LIVE_PERSONS_PRODUCT", ""),
                    "stripe_test": "prod_LipuNOM8jHV4Cn"
                },
                "limit": -1,
                "trial_limit": 100,
                "plans": {
                    "stripe_live": os.environ.get("STRIPE_LIVE_PERSONS_BASIC", ""),
                    "stripe_test": "price_1L1OEHKj0lYUbKAV6vArr8of"
                },
                "additional_properties": {
                    "free_usage": 100,
                    "usage_edge": 1000
                }
            }
        },
        "features": {},
        "flow": {                               # determine product changing flow
            "upgrade": ["platform-cloud-pro"],
            "downgrade": []
        }
    },
    "platform-cloud-pro": {
        "mode": "subscription",
        "period": "1m",
        "features": {},
        "meter_attributes": {
            "channels": {
                "products": {
                    "stripe_live": "",
                    "stripe_test": "prod_LiprPlI8T9HTzm"
                },
                "limit": -1,
                "plans": {
                    "stripe_live": "",
                    "stripe_test": "price_1L1OBzKj0lYUbKAVsq6a6wom"
                },
                "additional_properties": {}
            },
            "persons_in_base": {
                "products": {
                    "stripe_live": "",
                    "stripe_test": "prod_LipuNOM8jHV4Cn"
                },
                "limit": -1,
                "plans": {
                    "stripe_live": "",
                    "stripe_test": "price_1L1OEHKj0lYUbKAVVwp7KOLm"
                },
                "additional_properties": {
                    "free_usage": 100,
                    "usage_edge": 1000
                }
            }
        },
        "flow": {
            "upgrade": [],
            "downgrade": ["platform-cloud-basic"]
        }
    },
    "image-api-base": {
        "mode": "subscription",
        "period": "1m",
        "features": {},
        "meter_attributes": {
            "transactions": {
                "products": {
                    "stripe_live": os.environ.get("STRIPE_LIVE_IMAPI_PRODUCT", ""),
                    "stripe_test": "prod_Liv4tRhu42dkWl"
                },
                "limit": 50,
                "plans": {
                    "stripe_live": os.environ.get("STRIPE_LIVE_IMAPI_BASIC", ""),
                    "stripe_test": "price_1L1TEhKj0lYUbKAVpIlmnf7u"
                },
                "additional_properties": {}
            }
        },
        "flow": {
            "upgrade": ["image-api-startup", "image-api-expert", "image-api-advanced"],
            "downgrade": []
        }
    },
    "image-api-startup": {
        "mode": "subscription",
        "period": "1m",
        "features": {},
        "meter_attributes": {
            "transactions": {
                "products": {
                    "stripe_live": "",
                    "stripe_test": "prod_Liv4tRhu42dkWl"
                },
                "limit": -1,
                "plans": {
                    "stripe_live": "",
                    "stripe_test": "price_1L1TEhKj0lYUbKAV3dgv4Wso"
                },
                "additional_properties": {}
            }
        },
        "flow": {
            "upgrade": ["image-api-expert", "image-api-advanced"],
            "downgrade": ["image-api-base"]
        }
    },
    "image-api-expert": {
        "mode": "subscription",
        "period": "1m",
        "features": {},
        "meter_attributes": {
            "transactions": {
                "products": {
                    "stripe_live": "",
                    "stripe_test": "prod_Liv4tRhu42dkWl"
                },
                "limit": -1,
                "plans": {
                    "stripe_live": "",
                    "stripe_test": "price_1L1TEhKj0lYUbKAVUQoaWQFC"
                },
                "additional_properties": {}
            }
        },
        "flow": {
            "upgrade": ["image-api-advanced"],
            "downgrade": ["image-api-base", "image-api-startup"]
        }
    },
    "image-api-advanced": {
        "mode": "subscription",
        "period": "1m",
        "features": {},
        "meter_attributes": {
            "transactions": {
                "products": {
                    "stripe_live": "",
                    "stripe_test": "prod_Liv4tRhu42dkWl"
                },
                "limit": -1,
                "plans": {
                    "stripe_live": "",
                    "stripe_test": "price_1L1TEhKj0lYUbKAVxVKaMWEC"
                },
                "additional_properties": {}
            }
        },
        "flow": {
            "upgrade": [],
            "downgrade": ["image-api-base", "image-api-startup", "image-api-expert"]
        }
    }
}
