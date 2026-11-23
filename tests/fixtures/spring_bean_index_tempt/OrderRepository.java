package com.example;

import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data repo interface — never invent a proxy *Impl node. */
public interface OrderRepository extends JpaRepository<Order, Long> {
    Order findByRef(String ref);
}
