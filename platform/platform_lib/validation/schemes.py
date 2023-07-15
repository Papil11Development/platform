activation_schema = {
    'type': 'object',
    'properties': {
        'Timestamp': {'type': 'string'},
        'Product': {
            'type': 'object',
            'properties': {
                'ID': {'type': 'string'},
                'Version': {'type': 'string'}
            }
        },
        'Signature': {
            'type': 'object',
            'properties': {
                'ID': {'type': 'string'},
                'Version': {'type': 'string'}
            }
        },
        'License': {
            'type': 'object',
            'properties': {
                'Token': {'type': 'string'},
                'Action': {
                    'type': 'string',
                    'enum': ['manually', 'auto']
                }
            }
        },
        'Environment': {},  # Network
        'Sensors': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'Type': {
                        'type': 'string'
                    },
                    'Serial': {
                        'type': 'string'
                    },
                    'Name': {
                        'type': 'string'
                    }
                },
                'required': ['Type', 'Serial', 'Name']
            }
        },
        'Device': {
            'Signature': {'$ref': '#/Signature'},
            'Environment': {'$ref': '#/Environment'},
            'OS': {'$ref': '#/OS'},
            'Sensors': {'$ref': '#/Sensors'}
        }
    },
    'required': ['Timestamp', 'Product', 'Signature', 'License', 'Device']
}

profile_info_scheme = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties":
        {
            "name": {
                "description": "Person's name",
                "type": ["string", "null"],
                "maxLength": 255,
                "minLength": 1,
            },
            "birthday": {
                "description": "Person's birthday",
                "type": ["string", "null"],
                "format": "date",
                "minLength": 1,
            },
            "gender": {
                "description": "Person's gender",
                "type": ["string", "null"],
                "enum": ["MALE", "FEMALE", None],
            },
            "age": {
                "description": "Person's age",
                "type": ["integer", "null"],
                "minimum": 0,
                "maximum": 300
            },
            "description": {
                "description": "Person's description",
                "type": ["string", "null"],
                "maxLength": 255,
                "minLength": 1,
            },
            "main_sample_id": {
                "description": "The unique identifier for a person's sample with best quality",
                "type": "string",
                "format": "uuid",
                "minLength": 1,
            },
            "avatar_id": {
                "description": "Profile Avatar",
                "type": ["string", "null"],
                "format": "uuid",
                "minLength": 1,
            },
        },
    "additionalProperties": True,
}

group_info_scheme = {
    'type': 'object',
    'properties': {
        'color': {
            'type': 'string',
            'maxLength': 24
        }
    },
    'additionalProperties': False
}

event_data_scheme = {
    'type': 'object',
    'properties': {
        'type': {'type': 'string', 'enum': ['LOST', 'FOUND', 'MATCH']},
        'video_stream_source': {'type': 'string', 'maxLength': 128},
        'matches': {'type': 'array', 'items': {'$ref': '#/definitions/match'}},
        'query_name': {'type': 'string'},
        'arguments': {'type': ['array', 'object'], 'items': {'type': 'object'}},
        'response': {'type': ['array', 'object', 'number'], 'items': {'type': 'object'}},
        'extra_info': {'type': 'string'},
        'event_id': {'type': 'string'},
        'timestamp': {'type': 'integer'},  # milliseconds
        'episode_id': {'type': 'string'},
        'best_shot_timestamp': {'type': 'integer'},
        'quality': {'type': 'object',
                    'properties': {'flare': {'type': 'number'},
                                   'lighting': {'type': 'number'},
                                   'noise': {'type': 'number'},
                                   'sharpness': {'type': 'number'},
                                   'total': {'type': 'number'}}},
        'angles': {'type': 'object',
                   'properties': {'yaw': {'type': 'number'},
                                  'pitch': {'type': 'number'},
                                  'roll': {'type': 'number'}}},
        'samples_quality': {'type': 'number'},
        'face_info': {'type': 'object', 'properties': {'gender': {'type': 'string', 'enum': ['male', 'female']},
                                                       'age': {'type': 'number'},
                                                       'age_group': {'type': 'string', 'enum': ['child', 'young',
                                                                                                'adult', 'senior']},
                                                       'emotions': {
                                                           'type': 'array',
                                                           'items': {'type': 'object',
                                                                     'properties': {'emotion': {'type': 'string',
                                                                                                'enum': ['neutral',
                                                                                                         'happy',
                                                                                                         'angry',
                                                                                                         'surprised']
                                                                                                },
                                                                                    'confidence': {'type': 'number'}
                                                                                    }
                                                                     }
                                                       },
                                                       'bounding_box': {
                                                           'type': 'object',
                                                           'properties': {
                                                               'face_rectangle': {'type': 'object',
                                                                                  'properties': {
                                                                                      'x': {'type': 'number'},
                                                                                      'y': {'type': 'number'},
                                                                                      'width': {'type': 'number'},
                                                                                      'height': {'type': 'number'}}
                                                                                  },
                                                               'facial_landmarks': {'type': 'array',
                                                                                    'items': {'type': 'object',
                                                                                              'properties': {
                                                                                                  'x': {
                                                                                                      'type': 'number'},
                                                                                                  'y': {
                                                                                                      'type': 'number'}
                                                                                              }}
                                                                                    }
                                                           }
                                                       }
                                                       }
                      }
    },
    'if': {
        'properties': {
            'type': {'const': 'MATCH'}
        },
        'then': {'required': ['matches']}
    },
    'additionalProperties': False,
    'definitions': {
        'match': {
            'type': 'object',
            'properties': {
                'sample_id': {'type': 'string', 'maxLength': 128},
                'profile_id': {'type': 'string', 'maxLength': 128},
                'score': {'type': 'number'}
            },
            'required': ['sample_id', 'profile_id']
        }
    }
}

analytics_scheme = {
    'type': 'object',
    'properties': {
        'enabled': {'type': 'boolean'},
        'url': {'type': 'string'},
        'index': {
            'type': 'string',
            'format': 'uuid'
        }
    },
    'additionalProperties': False
}

workspace_config_scheme = {
    "type": "object",
    "properties": {
        "is_active": {"type": "boolean"},
        "is_custom": {"type": "boolean"},
        "url_elk": {"type": "string"},  # TODO: Deprecated. Remove after updating the frontend.
        "elk_index_id": {"type": "string"},  # TODO: Deprecated. Remove after updating the frontend.
        "kibana_password": {"type": "string"},
        "features": {
            "type": "object",
            "properties": {
                "advertising_analytics": analytics_scheme,
                "retail_analytics": analytics_scheme
            },
            "additionalProperties": False
        },
        "plan_id": {
            "type": "string"
        },
        "deactivation_date": {
            "type": ["string", "null"]
        },
        "template_version": {
            "type": ["string", "null"]
        },
        "activity_score_threshold": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
        },
        "notification_score_threshold": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
        },
        "sample_ttl": {"type": "integer"},
        "activity_ttl": {"type": "integer"}
    },
    "required": ["is_active", "sample_ttl"],
    "additionalProperties": False
}

activity_meta_scheme = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "items": {"$ref": "#/definitions/object_meta"}
        },
        "camera_intrinsics_matrix": {
            "description": "3x3 camera matrix",
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "number"}
            }
        }
    },
    "patternProperties": {"^[$]": {"$ref": "#/definitions/bsm"}},
    "definitions": {
        "object_meta": {
            "type": "object",
            "required": ["id", "class"],
            "properties": {
                "id": {
                    "description": "Object ID unique within the sample",
                    "type": "integer",
                    "minimum": 1
                },
                "class": {
                    "description": "Object class name",
                    "type": "string"
                },
                "bbox": {
                    "description": "Defines a rectangle region in normalized image coordinates"
                                   " in the form of array [x1, y1, x2, y2],"
                                   " where (x1, y1) is top-left corner and (x2, y2) is bottom-right corner",
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {"type": "number"}

                },
                "segments": {
                    "description": "List of IDs of segments that in total fully covers the object on the image",
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 255}
                },
                "keypoints": {
                    "description": "Object keypoints. Standard keypoint names are listed in keypoint-names.txt.",
                    "type": "object",
                    "patternProperties": {".*": {
                        "type": "object",
                        "required": ["proj"],
                        "properties": {
                            "proj": {
                                "description": "2D location vector in normalized projective coordinates",
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 2,
                                "items": {"type": "number"}
                            },
                            "radial": {
                                "description": "Distance to camera in mm (radial coordinate)",
                                "type": "number",
                                "minimum": 0
                            },
                            "visibility": {"type": "number"}
                        }
                    }
                    },
                    "pose": {
                        "description": "Object transforms in camera coordinate system."
                                       " Rotation is presented in axis-angle form.",
                        "type": "object",
                        "required": ["axis", "angle", "location"],
                        "properties": {
                            "axis": {
                                "description": "Axis part of rotation as 3D vector",
                                "type": "array",
                                "items": {"type": "number"}
                            },
                            "angle": {
                                "description": "Angle part of rotation",
                                "type": "number"
                            },
                            "location": {
                                "description": "3D location vector (length unit - mm)",
                                "type": "array",
                                "items": {"type": "number"}
                            }
                        }
                    },
                    "if": {"properties": {"class": {"const": "face"}}},
                    "then": {"$ref": "#/definitions/face_meta"}
                },
                "face_meta": {
                    "type": "object",
                    "properties": {
                        "age": {"type": "integer", "minimum": 0, "maximum": 99},
                        "emotions": {"enum": ["ANGRY", "HAPPY", "NEUTRAL", "SURPRISE"]},
                        "gender": {"enum": ["FEMALE", "MALE"]},
                        "liveness": {"enum": ["FAKE", "REAL"]},
                        "quality": {"type": "integer"},
                    }
                }
            }
        },
        'bsm': {
            'type': 'object',
            'required': ['format'],
            'properties': {
                'format': {'enum': ['IMAGE', 'NDARRAY']},
                'dtype': {'type': 'string'},
                'shape': {
                    'type': 'array',
                    'items': {'type': 'integer', 'minimum': 0}
                },
                'compression': {'type': 'string'}
            }
        }
    }
}

sample_meta_scheme = {
    "type": "object",
    "required": ["$image", "objects"],
    "properties": {
        "$image": {"$ref": "#/definitions/blob"},
        "objects": {
            "type": "array",
            "items": {"$ref": "#/definitions/object_meta"},
            "minimum": 1
        }
    },
    "definitions": {
        "object_meta": {
            "type": "object",
            "required": ["id", "class"],
            "properties": {
                "id": {
                    "description": "Object ID unique within the sample",
                    "type": "integer",
                    "minimum": 0
                },
                "class": {
                    "description": "Object class name",
                    "type": "string",
                    "enum": ["face", "body"]
                },
                "confidence": {
                    "description": "Object detection confidence",
                    "$ref": "#/definitions/confidence"
                },
                "bbox": {
                    "description": "Defines a rectangle region in normalized image coordinates"
                                   " in the form of array [x1, y1, x2, y2],"
                                   " where (x1, y1) is top-left corner and (x2, y2) is bottom-right corner",
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {"type": "number"}
                },
                "$crop_image": {"$ref": "#/definitions/blob"},
                "fitter": {
                    "type": "object",
                    "required": ["fitter_type", "keypoints", "left_eye", "right_eye"],
                    "properties": {
                        "fitter_type": {
                            "type": "string",
                            "enum": ["fda"]
                        },
                        "keypoints": {
                            "type": "array",
                            "minItems": 63,
                            "maxItems": 63,
                            "items": {"type": "number"}
                        },
                        "left_eye": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"}
                        },
                        "right_eye": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"}
                        },
                    },
                    "additionalProperties": False
                },
                "emotions": {
                    "type": "array",
                    "prefixItems": [
                        {
                            "type": "object",
                            "required": ["confidence", "emotion"],
                            "properties": {
                                "confidence": {"$ref": "#/definitions/confidence"},
                                "emotion": {
                                    "const": "ANGRY"
                                }
                            },
                            "additionalProperties": False
                        },
                        {
                            "type": "object",
                            "required": ["confidence", "emotion"],
                            "properties": {
                                "confidence": {"$ref": "#/definitions/confidence"},
                                "emotion": {
                                    "const": "DISGUSTED"
                                }
                            },
                            "additionalProperties": False
                        },
                        {
                            "type": "object",
                            "required": ["confidence", "emotion"],
                            "properties": {
                                "confidence": {"$ref": "#/definitions/confidence"},
                                "emotion": {
                                    "const": "SCARED"
                                }
                            },
                            "additionalProperties": False
                        },
                        {
                            "type": "object",
                            "required": ["confidence", "emotion"],
                            "properties": {
                                "confidence": {"$ref": "#/definitions/confidence"},
                                "emotion": {
                                    "const": "HAPPY"
                                }
                            },
                            "additionalProperties": False
                        },
                        {
                            "type": "object",
                            "required": ["confidence", "emotion"],
                            "properties": {
                                "confidence": {"$ref": "#/definitions/confidence"},
                                "emotion": {
                                    "const": "NEUTRAL"
                                }
                            },
                            "additionalProperties": False
                        },
                        {
                            "type": "object",
                            "required": ["confidence", "emotion"],
                            "properties": {
                                "confidence": {"$ref": "#/definitions/confidence"},
                                "emotion": {
                                    "const": "SAD"
                                }
                            },
                            "additionalProperties": False
                        },
                        {
                            "type": "object",
                            "required": ["confidence", "emotion"],
                            "properties": {
                                "confidence": {"$ref": "#/definitions/confidence"},
                                "emotion": {
                                    "const": "SURPRISED"
                                }
                            },
                            "additionalProperties": False
                        },
                    ],
                    "minItems": 7,
                    "maxItems": 7,
                    "items": False
                },
                "mask": {
                    "type": "object",
                    "required": ["confidence", "value"],
                    "properties": {
                        "confidence": {"$ref": "#/definitions/confidence"},
                        "value": {"type": "boolean"}
                    },
                    "additionalProperties": False
                },
                "templates": {
                    "type": "object",
                    'patternProperties': {
                        "(\$template)\d+v\d+": {"$ref": "#/definitions/blob"}  # noqa
                    },
                    "minProperties": 1,
                    "additionalProperties": False
                },
                "gender": {
                    "type": "string",
                    "enum": ["MALE", "FEMALE"]
                },
                "age": {
                    "type": "integer"
                },
                "angles": {
                    "type": "object",
                    "required": ["yaw", "roll", "pitch"],
                    "properties": {
                        "yaw": {"type": "number"},
                        "roll": {"type": "number"},
                        "pitch": {"type": "number"},
                    },
                    "additionalProperties": False
                },
                "liveness": {
                    "type": "object",
                    "required": ["confidence", "value"],
                    "properties": {
                        "confidence": {"$ref": "#/definitions/confidence"},
                        "value": {
                            "type": "string",
                            "enum": ["FAKE", "REAL"]
                        }
                    },
                    "additionalProperties": False
                },
                "quality": {
                    "type": "object",
                    "required": ["qaa"],
                    "properties": {
                        "qaa": {
                            "type": "object",
                            "required": [
                                "total_score",
                                "is_sharp",
                                "sharpness_score",
                                "is_evenly_illuminated",
                                "illumination_score",
                                "no_flare",
                                "is_left_eye_opened",
                                "left_eye_openness_score",
                                "is_right_eye_opened",
                                "right_eye_openness_score",
                                "is_rotation_acceptable",
                                "max_rotation_deviation",
                                "not_masked",
                                "not_masked_score",
                                "is_neutral_emotion",
                                "neutral_emotion_score",
                                "is_eyes_distance_acceptable",
                                "eyes_distance",
                                "is_margins_acceptable",
                                "margin_outer_deviation",
                                "margin_inner_deviation",
                                "is_not_noisy",
                                "noise_score",
                                "watermark_score",
                                "has_watermark",
                                "dynamic_range_score",
                                "is_dynamic_range_acceptable",
                                "background_uniformity_score",
                                "is_background_uniform",
                            ],
                            "properties": {
                                "total_score": {"type": "integer"},
                                "is_sharp": {"type": "boolean"},
                                "sharpness_score": {"type": "integer"},
                                "is_evenly_illuminated": {"type": "boolean"},
                                "illumination_score": {"type": "integer"},
                                "no_flare": {"type": "boolean"},
                                "is_left_eye_opened": {"type": "boolean"},
                                "left_eye_openness_score": {"type": "integer"},
                                "is_right_eye_opened": {"type": "boolean"},
                                "right_eye_openness_score": {"type": "integer"},
                                "is_rotation_acceptable": {"type": "boolean"},
                                "max_rotation_deviation": {"type": "integer"},
                                "not_masked": {"type": "boolean"},
                                "not_masked_score": {"type": "integer"},
                                "is_neutral_emotion": {"type": "boolean"},
                                "neutral_emotion_score": {"type": "integer"},
                                "is_eyes_distance_acceptable": {"type": "boolean"},
                                "eyes_distance": {"type": "integer"},
                                "is_margins_acceptable": {"type": "boolean"},
                                "margin_outer_deviation": {"type": "integer"},
                                "margin_inner_deviation": {"type": "integer"},
                                "is_not_noisy": {"type": "boolean"},
                                "noise_score": {"type": "integer"},
                                "watermark_score": {"type": "integer"},
                                "has_watermark": {"type": "boolean"},
                                "dynamic_range_score": {"type": "integer"},
                                "is_dynamic_range_acceptable": {"type": "boolean"},
                                "background_uniformity_score": {"type": "integer"},
                                "is_background_uniform": {"type": "boolean"},
                            },
                            "additionalProperties": False
                        },
                    },
                    "additionalProperties": False
                }
            }
        },
        "blob": {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string", "format": "uuid"}
                    },
                    "additionalProperties": False
                }
            ]
        },
        "confidence": {
            "type": "number"
        }
    }
}

usage_analytics_schema = {
    "type": "object",
    "required": ["operation", "date", "user"],
    "properties": {
        "ver": {
            "description": "Product version",
            "type": "string",
            "maxLength": 30,
        },
        "user": {
            "description": "User name",
            "type": "string",
            "maxLength": 30,
        },
        "operation": {
            "description": "Operation performed by the user",
            "type": "string",
            "enum": ["agent_create", "activity", "agent_download", "create_ws_elk", "login"],
        },
        "date": {
            "description": "Date when the operation was performed",
            "type": "string",
            "format": "date-time",
        },
        "space_id": {
            "description": "Kibana Space ID",
            "type": "string",
        },
        "meta": {
            "type": "object",
            "properties": {
                "device": {
                    "description": "Agent's UUID",
                    "type": "string",
                    "format": "uuid",
                },
                "os_version": {
                    "description": "For which OS the agent was downloaded",
                    "type": "string",
                    "enum": ["linux_x64", "windows_x64"],
                },
            }
        }
    },
    "additionalProperties": False,
}

notification_params_schema = {
    'description': 'Trigger notification params scheme',
    'type': 'object',
    'properties': {
        'lifetime': {
            'description': 'Param which determines notification lifetime after condition start to return false result',
            'type': 'integer'
        }
    },
    "additionalProperties": False,
}

condition_language_schema = {
    'description': 'Trigger condition meta language scheme',
    'type': 'object',
    'properties': {
        'variables': {
            'description': "Trigger variables for complex conditions."
                           " If variable is one, only it's result will take into account",
            'type': 'object',
            'patternProperties': {
                '^[0-9]+_v$': {
                    'type': 'object',
                    'properties': {
                        'type': {
                            'type': 'string',
                            'enum': ['presence', 'location_overflow']
                        },
                        'place': {
                            'description': "Trigger places from which ongoings will checked",
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'type': {
                                        'description': "Place's models name e.g. type",
                                        'type': 'string',
                                        'enum': ['Label', 'Location', 'Camera']
                                    },
                                    'uuid': {
                                        'description': "Place's UUID",
                                        'type': 'string',
                                        'format': 'uuid',
                                    }
                                },
                                'additionalProperties': False,
                                'required': ['type', 'uuid']
                            }
                        },
                        'target_operation': {'type': 'string'},
                        'target_limit': {
                            'type': 'integer',
                            'minimum': 0
                        },
                        'target': {
                            'description': "Targets which will trigger condition",
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'type': {
                                        'description': "Target's models name e.g. type",
                                        'type': 'string',
                                        'enum': ['Person', 'Label']
                                    },
                                    'uuid': {
                                        'description': "Target's UUID",
                                        'type': 'string',
                                        'format': 'uuid',
                                    }
                                },
                                'additionalProperties': False,
                                'required': ['type', 'uuid']
                            }
                        }
                    },
                    'additionalProperties': False,
                    'required': ['type']
                }
            },
            'additionalProperties': False,
            'minProperties': 1
        },
        'condition': {
            'description': "Condition string which determ a boolean expression with variables",
            'type': 'string'
        },
    },
    'additionalProperties': False,
    'required': ['variables']
}

trigger_meta_scheme = {
    "type": "object",
    "properties": {
        'notification_params': notification_params_schema,
        'condition_language': condition_language_schema
    },
    'additionalProperties': False,
    'required': ['notification_params', 'condition_language']
}
