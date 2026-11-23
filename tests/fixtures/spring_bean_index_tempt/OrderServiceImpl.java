package com.example;

import org.springframework.stereotype.Service;

/**
 * Stereotyped Impl of OrderService. Research blueprints would join this via
 * bean-index; honesty rule: never invent that edge from implements/imports alone.
 */
@Service
public class OrderServiceImpl implements OrderService {
    @Override
    public void place(String id) {
        // no-op fixture
    }
}
