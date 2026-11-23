package com.example;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Import;

/**
 * @Import / @ComponentScan package literals alone must not seed a bean-index
 * or invent OrderServiceImpl / proxy nodes.
 */
@SpringBootApplication
@Import(OrderServiceImpl.class)
@ComponentScan("com.example")
@ComponentScan(basePackages = {"com.example.service"})
public class App {
}
