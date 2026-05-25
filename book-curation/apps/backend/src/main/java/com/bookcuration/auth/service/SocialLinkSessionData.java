package com.taeo.bookcuration.auth.service;

import java.io.Serializable;
import java.util.UUID;

public record SocialLinkSessionData(
        UUID userId,
        String provider
) implements Serializable {
}
