package com.taeo.bookcuration.security.ratelimit;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

class CachedBodyHttpServletRequest extends HttpServletRequestWrapper {

    private final byte[] cachedBody;

    CachedBodyHttpServletRequest(HttpServletRequest request, int maxBytes) throws IOException {
        super(request);
        this.cachedBody = readUpTo(request.getInputStream(), maxBytes);
    }

    byte[] getCachedBody() {
        return cachedBody.clone();
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(cachedBody);
        return new ServletInputStream() {
            @Override
            public boolean isFinished() {
                return byteArrayInputStream.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener readListener) {
                // 수정 포인트: 동기 MVC 요청에서 사용하므로 별도 비동기 리스너 처리는 필요하지 않습니다.
            }

            @Override
            public int read() {
                return byteArrayInputStream.read();
            }
        };
    }

    @Override
    public BufferedReader getReader() {
        Charset charset = getCharacterEncoding() == null
                ? StandardCharsets.UTF_8
                : Charset.forName(getCharacterEncoding());
        return new BufferedReader(new InputStreamReader(getInputStream(), charset));
    }

    private byte[] readUpTo(InputStream inputStream, int maxBytes) throws IOException {
        byte[] buffer = inputStream.readNBytes(maxBytes + 1);
        if (buffer.length > maxBytes) {
            throw new IOException("요청 본문이 rate limit 검사용 허용 크기를 초과했습니다.");
        }
        return buffer;
    }
}
