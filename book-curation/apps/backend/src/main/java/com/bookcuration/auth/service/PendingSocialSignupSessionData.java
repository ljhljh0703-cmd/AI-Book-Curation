package com.taeo.bookcuration.auth.service;

import java.io.Serializable;

public record PendingSocialSignupSessionData(
        String provider,
        String providerUserId,
        String providerEmail,
        String nickname
) implements Serializable {
}
